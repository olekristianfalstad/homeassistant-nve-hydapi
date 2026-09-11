"""Regression tests for HydAPI response identity and authentication."""

from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientResponseError

from custom_components.nve_hydapi.api import (
    NveHydApiAuthError,
    NveHydApiClient,
    NveHydApiError,
    series_key,
)


def series(station="139.15.0", parameter=1001, resolution="0", version=1):
    return {
        "station_id": station,
        "parameter": parameter,
        "resolution_time": resolution,
        "version_number": version,
    }


def observation(config, value, version=1):
    return {
        "stationId": config["station_id"],
        "parameter": config["parameter"],
        "serieVersionNo": version,
        "observations": [
            {"value": value, "time": "2026-09-11T11:00:00Z", "quality": 1}
        ],
    }


class ApiTests(IsolatedAsyncioTestCase):
    async def test_different_stations_and_parameters_use_one_request(self):
        selected = [series(), series("1.2.0"), series(parameter=1003)]
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock(return_value={
            "data": [observation(item, index) for index, item in reversed(list(enumerate(selected)))]
        })
        data = await client.async_fetch_observations(selected)
        self.assertEqual([data[series_key(item)]["value"] for item in selected], [0, 1, 2])
        client._request.assert_awaited_once()
        self.assertEqual(len(client._request.call_args.kwargs["json"]), 3)

    async def test_resolutions_are_separated_and_missing_series_does_not_shift(self):
        instant = series()
        daily = series(resolution="1440")
        other = series("1.2.0")
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock(side_effect=[
            {"data": [observation(other, 7)]},
            {"data": [observation(daily, 80)]},
        ])
        data = await client.async_fetch_observations([instant, daily, other])
        self.assertIsNone(data[series_key(instant)]["value"])
        self.assertEqual(data[series_key(daily)]["value"], 80)
        self.assertEqual(data[series_key(other)]["value"], 7)
        bodies = [call.kwargs["json"] for call in client._request.call_args_list]
        self.assertEqual([len(body) for body in bodies], [2, 1])
        self.assertEqual(bodies[1][0]["resolutionTime"], "1440")

    async def test_all_three_resolutions_keep_their_own_values(self):
        selected = [series(resolution=r) for r in ("1440", "0", "60")]
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock(side_effect=[
            {"data": [observation(item, value)]}
            for item, value in zip(selected, [80, 120, 100], strict=True)
        ])
        data = await client.async_fetch_observations(selected)
        self.assertEqual(
            {item["resolution_time"]: data[series_key(item)]["value"] for item in selected},
            {"1440": 80, "0": 120, "60": 100},
        )

    async def test_wrong_or_missing_version_is_not_assigned(self):
        selected = series()
        client = NveHydApiClient(Mock(), "test-key")
        for returned_version in (2, None):
            with self.subTest(version=returned_version):
                client._request = AsyncMock(return_value={
                    "data": [observation(selected, 999, version=returned_version)]
                })
                data = await client.async_fetch_observations([selected])
                self.assertIsNone(data[series_key(selected)]["value"])

    async def test_automatic_and_explicit_versions_are_kept_separate(self):
        selected = [series(version=None), series(version=0)]
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock(side_effect=[
            {"data": [observation(selected[0], 120, version=2)]},
            {"data": [observation(selected[1], 80, version=0)]},
        ])
        data = await client.async_fetch_observations(selected)
        self.assertEqual([data[series_key(item)]["value"] for item in selected], [120, 80])
        self.assertEqual(client._request.await_count, 2)
        self.assertEqual(client._request.call_args.kwargs["json"][0]["versionNumber"], 0)

    async def test_duplicate_response_is_rejected(self):
        selected = series()
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock(return_value={
            "data": [observation(selected, 1), observation(selected, 2)]
        })
        with self.assertRaises(NveHydApiError):
            await client.async_fetch_observations([selected])

    async def test_empty_selection_makes_no_request(self):
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock()
        self.assertEqual(await client.async_fetch_observations([]), {})
        client._request.assert_not_awaited()

    async def test_unrequested_station_is_ignored(self):
        selected = series()
        client = NveHydApiClient(Mock(), "test-key")
        client._request = AsyncMock(return_value={"data": [observation(series("1.2.0"), 42)]})
        data = await client.async_fetch_observations([selected])
        self.assertIsNone(data[series_key(selected)]["value"])

    async def test_validation_uses_small_authenticated_parameter_request(self):
        response = Mock()
        response.json = AsyncMock(return_value={"data": []})
        session = Mock()
        session.request = AsyncMock(return_value=response)
        await NveHydApiClient(session, "new-test-key").async_validate_api_key()
        args, kwargs = session.request.call_args
        self.assertEqual(args, ("GET", "https://hydapi.nve.no/api/v1/Parameters"))
        self.assertEqual(kwargs["headers"]["X-API-Key"], "new-test-key")

    async def test_rejected_keys_raise_auth_error(self):
        for status in (401, 403):
            with self.subTest(status=status):
                response = Mock()
                response.raise_for_status.side_effect = ClientResponseError(
                    Mock(), (), status=status
                )
                session = Mock()
                session.request = AsyncMock(return_value=response)
                with self.assertRaises(NveHydApiAuthError):
                    await NveHydApiClient(session, "bad-test-key").async_validate_api_key()
