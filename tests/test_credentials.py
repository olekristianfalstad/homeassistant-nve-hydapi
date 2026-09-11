"""Exercise real Home Assistant flow/coordinator helpers with mocked I/O."""

import tempfile
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.nve_hydapi.api import NveHydApiAuthError, NveHydApiError
from custom_components.nve_hydapi.config_flow import NveHydApiConfigFlow
from custom_components.nve_hydapi.coordinator import NveHydApiCoordinator
from custom_components.nve_hydapi.sensor import NveHydApiSensor


class CredentialTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        self.entry = Mock()
        self.entry.entry_id = "existing-entry"
        self.entry.title = "NVE HydAPI"
        self.entry.data = {"api_key": "old-test-key", "unrelated": "preserve"}
        self.entry.options = {
            "scan_interval": 15,
            "series": [{
                "station_id": "139.15.0",
                "station_name": "Bjornstad",
                "parameter": 1001,
                "resolution_time": "0",
                "version_number": 1,
            }],
        }
        self.entry.pref_disable_polling = False
        self.hass.config_entries = Mock()
        self.hass.config_entries.async_get_known_entry.return_value = self.entry
        self.flow = NveHydApiConfigFlow()
        self.flow.hass = self.hass
        self.flow.context = {"source": "reconfigure", "entry_id": self.entry.entry_id}
        self.client_patch = patch(
            "custom_components.nve_hydapi.config_flow.NveHydApiClient"
        )
        self.client_type = self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.client = self.client_type.return_value
        self.client.async_validate_api_key = AsyncMock()
        session_patch = patch(
            "custom_components.nve_hydapi.config_flow.async_get_clientsession",
            return_value=Mock(),
        )
        session_patch.start()
        self.addCleanup(session_patch.stop)

    async def test_opening_or_cancelling_does_not_expose_or_replace_key(self):
        result = await self.flow.async_step_reconfigure()
        self.assertEqual(result["type"], FlowResultType.FORM)
        self.assertEqual(result["step_id"], "reconfigure")
        self.assertNotIn("old-test-key", str(result))
        self.hass.config_entries.async_update_entry.assert_not_called()
        self.client.async_validate_api_key.assert_not_awaited()
        selector = next(iter(result["data_schema"].schema.values()))
        self.assertEqual(selector.config["type"], "password")

    async def test_reconfigure_preserves_options_identity_and_other_data(self):
        options_before = self.entry.options.copy()
        result = await self.flow.async_step_reconfigure({"api_key": "  new-test-key  "})
        self.assertEqual(result["type"], FlowResultType.ABORT)
        self.assertEqual(result["reason"], "reconfigure_successful")
        update = self.hass.config_entries.async_update_entry.call_args.kwargs
        self.assertIs(update["entry"], self.entry)
        self.assertEqual(update["data"], {"api_key": "new-test-key", "unrelated": "preserve"})
        self.assertEqual(self.entry.options, options_before)
        self.assertNotIsInstance(update["options"], dict)
        self.client.async_validate_api_key.assert_awaited_once()
        self.assertEqual(self.client_type.call_args.args[1], "new-test-key")
        self.hass.config_entries.async_schedule_reload.assert_called_once_with("existing-entry")

    async def test_reauth_uses_same_entry_and_requires_valid_replacement(self):
        self.flow.context["source"] = "reauth"
        form = await self.flow.async_step_reauth(self.entry.data)
        self.assertEqual(form["step_id"], "reauth_confirm")
        result = await self.flow.async_step_reauth_confirm({"api_key": "new-test-key"})
        self.assertEqual(result["reason"], "reauth_successful")
        self.assertIs(
            self.hass.config_entries.async_update_entry.call_args.kwargs["entry"],
            self.entry,
        )

    async def test_invalid_key_and_network_failure_leave_entry_untouched(self):
        for source in ("reconfigure", "reauth"):
            self.flow.context["source"] = source
            step = (
                self.flow.async_step_reconfigure if source == "reconfigure"
                else self.flow.async_step_reauth_confirm
            )
            for error, expected in (
                (NveHydApiAuthError(), "invalid_auth"),
                (NveHydApiError(), "cannot_connect"),
                (TimeoutError(), "cannot_connect"),
            ):
                with self.subTest(source=source, error=type(error).__name__):
                    self.client.async_validate_api_key.side_effect = error
                    result = await step({"api_key": "bad-test-key"})
                    self.assertEqual(result["errors"], {"base": expected})
                    self.assertEqual(self.entry.data["api_key"], "old-test-key")
                    self.hass.config_entries.async_update_entry.assert_not_called()
                    self.hass.config_entries.async_schedule_reload.assert_not_called()

    async def test_blank_key_does_not_make_network_request(self):
        result = await self.flow.async_step_reconfigure({"api_key": "   "})
        self.assertEqual(result["errors"], {"api_key": "invalid_auth"})
        self.client.async_validate_api_key.assert_not_awaited()

    async def test_coordinator_links_entry_and_preserves_sensor_identity(self):
        client = Mock()
        coordinator = NveHydApiCoordinator(self.hass, self.entry, client)
        self.assertIs(coordinator.config_entry, self.entry)
        self.assertEqual(coordinator.update_interval.total_seconds(), 900)
        self.entry.async_on_unload.assert_called()
        sensor = NveHydApiSensor(coordinator, self.entry.options["series"][0])
        self.assertEqual(sensor.unique_id, "nve_hydapi_139.15.0|1001|0|1")

    async def test_auth_error_is_distinct_from_transient_failure(self):
        client = Mock()
        client.async_fetch_observations = AsyncMock(side_effect=NveHydApiAuthError())
        coordinator = NveHydApiCoordinator(self.hass, self.entry, client)
        with self.assertRaises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
        client.async_fetch_observations.side_effect = NveHydApiError()
        with self.assertRaises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_polling_rejection_starts_home_assistant_reauth(self):
        client = Mock()
        client.async_fetch_observations = AsyncMock(side_effect=NveHydApiAuthError())
        coordinator = NveHydApiCoordinator(self.hass, self.entry, client)
        await coordinator.async_refresh()
        self.assertFalse(coordinator.last_update_success)
        self.entry.async_start_reauth.assert_called_once_with(self.hass)
