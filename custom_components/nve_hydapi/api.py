"""Client for NVE HydAPI."""

from __future__ import annotations

import re
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

from .const import HYDAPI_BASE_URL

STATION_ID_RE = re.compile(r"^\d+\.\d+\.(\d+|\*)$")


class NveHydApiError(Exception):
    """Base error for NVE HydAPI."""


class NveHydApiAuthError(NveHydApiError):
    """Authentication failed."""


class NveHydApiRateLimitError(NveHydApiError):
    """HydAPI rate limit was reached."""


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

    async def async_validate_api_key(self) -> None:
        """Validate that the API key can call HydAPI."""
        await self._request("GET", "/Parameters")

    async def async_search_series(self, query: str) -> list[dict[str, Any]]:
        """Search series by station id or station name."""
        query = query.strip()
        params: dict[str, str] = {}

        if STATION_ID_RE.match(query):
            params["StationId"] = query
        else:
            params["StationName"] = query

        result = await self._request("GET", "/Series", params=params)
        return result.get("data") or []

    async def async_fetch_observations(
        self, selected_series: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Fetch latest observations for all selected series in one POST request."""
        if not selected_series:
            return {}

        body = []
        for item in selected_series:
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
        response_series = result.get("data") or []
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

        unmatched_keys = list(values)
        for data_item in response_series:
            key = self._match_response_to_config(data_item, values, unmatched_keys)
            if key is None:
                continue

            observations = data_item.get("observations") or []
            latest = observations[-1] if observations else {}
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
        """Call HydAPI and return decoded JSON."""
        headers = {
            "Accept": "application/json",
            "X-API-Key": self._api_key,
        }

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
            return await response.json()
        except ClientResponseError as err:
            if err.status in (401, 403):
                raise NveHydApiAuthError("HydAPI rejected the API key") from err
            if err.status == 429:
                raise NveHydApiRateLimitError("HydAPI rate limit reached") from err
            raise NveHydApiError(f"HydAPI returned HTTP {err.status}") from err
        except ClientError as err:
            raise NveHydApiError("Could not connect to HydAPI") from err

    @staticmethod
    def _match_response_to_config(
        data_item: dict[str, Any],
        values: dict[str, dict[str, Any]],
        unmatched_keys: list[str],
    ) -> str | None:
        """Match a HydAPI response item to one configured sensor."""
        station_id = str(data_item.get("stationId") or "")
        parameter = str(data_item.get("parameter") or "")
        version = data_item.get("serieVersionNo")

        candidates: list[str] = []
        for key in unmatched_keys:
            config = values[key]["series"]
            if config["station_id"] != station_id:
                continue
            if str(config["parameter"]) != parameter:
                continue
            config_version = config.get("version_number")
            if config_version is not None and version is not None:
                if int(config_version) != int(version):
                    continue
            candidates.append(key)

        if not candidates:
            return None

        key = candidates[0]
        unmatched_keys.remove(key)
        return key
