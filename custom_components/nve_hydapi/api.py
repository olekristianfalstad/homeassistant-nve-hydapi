"""Client for NVE HydAPI."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from time import monotonic
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout, ContentTypeError

from .const import HYDAPI_BASE_URL
from .observation import observation_time

STATION_CACHE_SECONDS = 4 * 60 * 60

class NveHydApiError(Exception):
    """Base error for NVE HydAPI."""


class NveHydApiAuthError(NveHydApiError):
    """Authentication failed."""


class NveHydApiRateLimitError(NveHydApiError):
    """HydAPI rate limit was reached."""


class NveHydApiTimeoutError(NveHydApiError):
    """HydAPI did not respond in time."""


class NveHydApiResponseError(NveHydApiError):
    """HydAPI returned an unreadable or malformed response."""


def _retry_delay(headers: Any) -> float:
    """Read standard Retry-After and HydAPI reset timestamps conservatively."""
    delays = []
    now = datetime.now(UTC)
    for name in ("Retry-After", "x-rate-limit-reset"):
        value = headers.get(name) if headers else None
        if not isinstance(value, str):
            continue
        try:
            number = float(value)
            delay = number if name == "Retry-After" else number - now.timestamp()
        except ValueError:
            try:
                reset = observation_time(value) or parsedate_to_datetime(value)
                delay = (reset - now).total_seconds()
            except (TypeError, ValueError, OverflowError):
                continue
        if isfinite(delay) and delay > 0:
            delays.append(delay)
    return max(delays, default=600)


def series_key(series: dict[str, Any]) -> str:
    """Return a stable key for a selected series."""
    station_id = series["station_id"]
    parameter = str(series["parameter"])
    resolution_time = str(series["resolution_time"])
    version = series.get("version_number")
    version_part = "" if version is None else str(version)
    return f"{station_id}|{parameter}|{resolution_time}|{version_part}"


class NveHydApiClient:
    """Small async HydAPI client."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_key = api_key
        self._blocked_until = 0.0
        self._stations: list[dict[str, Any]] | None = None
        self._stations_expire = 0.0
        self._station_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    async def async_get_active_stations(self) -> list[dict[str, Any]]:
        """Return all active HydAPI stations."""
        async with self._station_lock:
            if self._stations is None or monotonic() >= self._stations_expire:
                result = await self._request(
                    "GET", "/Stations", params={"Active": "OnlyActive"}
                )
                self._stations = result["data"]
                self._stations_expire = monotonic() + STATION_CACHE_SECONDS
            return deepcopy(self._stations)

    async def async_validate_api_key(self) -> None:
        """Validate credentials using the small parameter catalogue."""
        await self._request("GET", "/Parameters")

    async def async_get_station_series(
        self, station_id: str
    ) -> list[dict[str, Any]]:
        """Return all series belonging to one station."""
        result = await self._request(
            "GET", "/Series", params={"StationId": station_id}
        )
        return result.get("data") or []

    async def async_fetch_observations(
        self, selected_series: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Fetch latest observations in batches with unambiguous identities."""
        if not selected_series:
            return {}

        values = {
            series_key(item): {
                "series": item,
                "value": None,
                "time": None,
                "quality": None,
                "correction": None,
                "raw": None,
            }
            for item in selected_series
        }

        # HydAPI does not echo resolutionTime. Put repeated station/parameter
        # combinations in separate batches, even if their versions differ.
        groups: dict[tuple[str, str], list[str]] = {}
        for key, value in values.items():
            item = value["series"]
            identity = (str(item["station_id"]), str(item["parameter"]))
            groups.setdefault(identity, []).append(key)

        for index in range(max(len(keys) for keys in groups.values())):
            batch = {
                keys[index]: values[keys[index]]
                for keys in groups.values()
                if index < len(keys)
            }
            body = []
            for value in batch.values():
                item = value["series"]
                request_item: dict[str, Any] = {
                    "stationId": item["station_id"],
                    "parameter": str(item["parameter"]),
                    "resolutionTime": str(item["resolution_time"]),
                }
                if item.get("version_number") is not None:
                    request_item["versionNumber"] = item["version_number"]
                if item.get("reference_time"):
                    request_item["referenceTime"] = item["reference_time"]
                body.append(request_item)

            result = await self._request("POST", "/Observations", json=body)
            seen: set[str] = set()
            for data_item in result.get("data") or []:
                key = self._match_response_to_config(data_item, batch)
                if key is None:
                    continue
                if key in seen:
                    raise NveHydApiError("HydAPI returned duplicate series")
                seen.add(key)

                observations = data_item.get("observations") or []
                if not isinstance(observations, list) or any(
                    not isinstance(item, dict) for item in observations
                ):
                    raise NveHydApiResponseError("Invalid observations list")
                latest = max(
                    observations,
                    key=lambda item: observation_time(item.get("time"))
                    or datetime.min.replace(tzinfo=UTC),
                    default={},
                )
                values[key] = {
                    "series": values[key]["series"],
                    "value": latest.get("value"),
                    "time": latest.get("time"),
                    "quality": latest.get("quality"),
                    "correction": latest.get("correction"),
                    "raw": data_item,
                }

        return values

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: Any | None = None,
    ) -> dict[str, Any]:
        """Serialize requests so all flows respect the same rate-limit window."""
        async with self._request_lock:
            if monotonic() < self._blocked_until:
                raise NveHydApiRateLimitError("HydAPI retry window has not elapsed")
            return await self._perform_request(method, path, params=params, json=json)

    async def _perform_request(
        self, method: str, path: str, *,
        params: dict[str, str] | None, json: Any | None,
    ) -> dict[str, Any]:
        """Call HydAPI and return decoded JSON."""
        headers = {
            "Accept": "application/json",
            "X-API-Key": self._api_key,
        }

        response = None
        try:
            response = await self._session.request(
                method,
                f"{HYDAPI_BASE_URL}{path}",
                headers=headers,
                params=params,
                json=json,
                timeout=ClientTimeout(total=30),
            )
            response.raise_for_status()
            if response.headers.get("x-rate-limit-remaining") == "0":
                self._blocked_until = monotonic() + _retry_delay(response.headers)
            result = await response.json()
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("data"), list)
                or any(not isinstance(item, dict) for item in result["data"])
            ):
                raise NveHydApiResponseError("Invalid HydAPI response structure")
            return result
        except (ContentTypeError, ValueError) as err:
            raise NveHydApiResponseError("HydAPI returned invalid JSON") from err
        except TimeoutError as err:
            raise NveHydApiTimeoutError("HydAPI request timed out") from err
        except ClientResponseError as err:
            if err.status in (401, 403):
                self._stations = None
                raise NveHydApiAuthError("HydAPI rejected the API key") from err
            if err.status == 429:
                self._blocked_until = monotonic() + _retry_delay(err.headers)
                raise NveHydApiRateLimitError("HydAPI rate limit reached") from err
            raise NveHydApiError(f"HydAPI returned HTTP {err.status}") from err
        except ClientError as err:
            raise NveHydApiError("Could not connect to HydAPI") from err
        finally:
            if response is not None:
                response.release()

    @staticmethod
    def _match_response_to_config(
        data_item: dict[str, Any],
        values: dict[str, dict[str, Any]],
    ) -> str | None:
        """Match a HydAPI response item to one configured sensor."""
        station_id = str(data_item.get("stationId") or "")
        parameter = str(data_item.get("parameter") or "")
        version = data_item.get("serieVersionNo")

        candidates: list[str] = []
        for key, value in values.items():
            config = value["series"]
            if str(config["station_id"]) != station_id:
                continue
            if str(config["parameter"]) != parameter:
                continue
            config_version = config.get("version_number")
            if config_version is not None and str(config_version) != str(version):
                continue
            candidates.append(key)

        if len(candidates) != 1:
            return None

        return candidates[0]
