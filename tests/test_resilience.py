"""Transport boundaries, caching and rate limiting use no live NVE services."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientResponseError

from custom_components.nve_hydapi.api import (
    NveHydApiClient, NveHydApiRateLimitError, NveHydApiResponseError,
    NveHydApiTimeoutError, _retry_delay,
)


class ResilienceTests(IsolatedAsyncioTestCase):
    def make_client(self):
        self.response = Mock(headers={})
        self.response.json = AsyncMock(return_value={"data": []})
        self.session = Mock()
        self.session.request = AsyncMock(return_value=self.response)
        return NveHydApiClient(self.session, "test-key")

    async def test_timeout_at_connect_and_decode_is_normalized(self):
        for at_decode in (False, True):
            with self.subTest(at_decode=at_decode):
                client = self.make_client()
                target = self.response.json if at_decode else self.session.request
                target.side_effect = TimeoutError()
                with self.assertRaises(NveHydApiTimeoutError):
                    await client.async_validate_api_key()
                if at_decode:
                    self.response.release.assert_called_once()

    async def test_invalid_json_and_shapes_are_normalized_and_released(self):
        for payload in (None, [], {}, {"data": {}}, {"data": [None]}, {"data": [1]}):
            with self.subTest(payload=payload):
                client = self.make_client()
                self.response.json.return_value = payload
                with self.assertRaises(NveHydApiResponseError):
                    await client.async_validate_api_key()
                self.response.release.assert_called_once()
        self.response.json.side_effect = ValueError("not JSON")
        with self.assertRaises(NveHydApiResponseError):
            await client.async_validate_api_key()

    async def test_cancellation_propagates_and_releases_response(self):
        client = self.make_client()
        self.response.json.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await client.async_validate_api_key()
        self.response.release.assert_called_once()

    async def test_rate_limit_blocks_all_endpoints_until_retry_time(self):
        client = self.make_client()
        self.response.raise_for_status.side_effect = ClientResponseError(
            Mock(), (), status=429, headers={"Retry-After": "120"}
        )
        with patch("custom_components.nve_hydapi.api.monotonic", return_value=1000):
            with self.assertRaises(NveHydApiRateLimitError):
                await client.async_validate_api_key()
            with self.assertRaises(NveHydApiRateLimitError):
                await client.async_get_active_stations()
        self.session.request.assert_awaited_once()
        self.response.raise_for_status.side_effect = None
        with patch("custom_components.nve_hydapi.api.monotonic", return_value=1121):
            await client.async_get_active_stations()
        self.assertEqual(self.session.request.await_count, 2)

    async def test_retry_header_formats_and_fallback(self):
        later = datetime.now(UTC) + timedelta(minutes=10)
        for name, value in (
            ("Retry-After", "600"), ("Retry-After", format_datetime(later)),
            ("x-rate-limit-reset", later.isoformat()),
            ("x-rate-limit-reset", str(later.timestamp())),
        ):
            self.assertAlmostEqual(_retry_delay({name: value}), 600, delta=2)
        for value in ("garbage", "NaN", "-1"):
            self.assertEqual(_retry_delay({"Retry-After": value}), 600)

    async def test_last_allowed_response_starts_cooldown(self):
        client = self.make_client()
        self.response.headers = {"x-rate-limit-remaining": "0", "Retry-After": "600"}
        await client.async_validate_api_key()
        with self.assertRaises(NveHydApiRateLimitError):
            await client.async_validate_api_key()
        self.session.request.assert_awaited_once()

    async def test_station_cache_expires_and_returns_independent_copies(self):
        client = self.make_client()
        self.response.json.return_value = {"data": [{"stationId": "1.2.0"}]}
        with patch("custom_components.nve_hydapi.api.monotonic", return_value=1000):
            first, second = await asyncio.gather(
                client.async_get_active_stations(), client.async_get_active_stations()
            )
            first[0]["stationId"] = "changed"
            self.assertEqual(second[0]["stationId"], "1.2.0")
            await client.async_get_active_stations()
            self.session.request.assert_awaited_once()
        with patch("custom_components.nve_hydapi.api.monotonic", return_value=15401):
            await client.async_get_active_stations()
        self.assertEqual(self.session.request.await_count, 2)

    async def test_failed_station_request_is_not_cached(self):
        client = self.make_client()
        self.session.request.side_effect = TimeoutError()
        with self.assertRaises(NveHydApiTimeoutError):
            await client.async_get_active_stations()
        self.session.request.side_effect = None
        await client.async_get_active_stations()
        self.assertEqual(self.session.request.await_count, 2)
