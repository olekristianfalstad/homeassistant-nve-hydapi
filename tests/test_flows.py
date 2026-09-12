"""Form regressions, including cancellation and localised resolution labels."""

import tempfile
from copy import deepcopy
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.nve_hydapi.api import NveHydApiTimeoutError, NveHydApiResponseError, NveHydApiRateLimitError, series_key
from custom_components.nve_hydapi.config_flow import NveHydApiConfigFlow, NveHydApiOptionsFlow, _station_id_from_selection

SERIES = {"station_id": "139.15.0", "station_name": "Bjornstad", "parameter": 1001,
          "parameter_name": "Vannforing", "resolution_time": "1440", "version_number": 1}


class FlowTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.hass = HomeAssistant(directory.name)
        self.entry = Mock(entry_id="entry", data={"api_key": "test-key"}, options={"series": [deepcopy(SERIES)], "scan_interval": 15})
        translations = patch(
            "custom_components.nve_hydapi.config_flow._resolution_labels",
            new=AsyncMock(return_value={"0": "Momentan", "60": "Time", "1440": "D\u00f8gn"})
        )
        translations.start()
        self.addCleanup(translations.stop)
        factory = patch("custom_components.nve_hydapi.config_flow.get_client")
        self.client = factory.start().return_value
        self.addCleanup(factory.stop)

    def flow(self, options=False):
        flow = NveHydApiOptionsFlow(self.entry) if options else NveHydApiConfigFlow()
        flow.hass = self.hass
        flow._api_key = "test-key"
        flow._station_options = {"139.15.0": "Bjornstad [139.15.0] - Namsskogan"}
        return flow

    async def test_station_failures_return_retryable_forms_in_both_flows(self):
        for options in (False, True):
            for error, key in ((NveHydApiTimeoutError(), "timeout"), (NveHydApiResponseError(), "invalid_response"), (NveHydApiRateLimitError(), "rate_limited")):
                flow = self.flow(options)
                self.client.async_get_station_series = AsyncMock(side_effect=error)
                result = await flow.async_step_station({"station_id": "139.15.0"})
                self.assertEqual(result["step_id"], "station")
                self.assertEqual(result["errors"], {"base": key})

    async def test_station_selection_preserves_display_label(self):
        flow = self.flow()
        form = await flow.async_step_station()
        selector = next(iter(form["data_schema"].schema.values()))
        label = selector.config["options"][0]
        self.assertIn("Bjornstad", label)
        self.assertTrue(selector.config["custom_value"])
        self.assertEqual(_station_id_from_selection(label, flow._station_options), "139.15.0")
        self.assertIsNone(_station_id_from_selection("made-up", flow._station_options))

    async def test_multi_select_deduplicates_and_continue_can_save(self):
        flow = self.flow(True)
        second = {**SERIES, "resolution_time": "0"}
        flow._choices = {series_key(s): s for s in (SERIES, second)}
        result = await flow.async_step_series({"series": list(flow._choices), "add_another": True})
        self.assertEqual(result["step_id"], "continue")
        self.assertEqual(len(self.entry.options["series"]), 1)
        saved = await flow.async_step_continue({"add_another": False})
        self.assertEqual(len(saved["data"]["series"]), 2)

    async def test_empty_and_unknown_series_cannot_be_saved(self):
        for options in (False, True):
            flow = self.flow(options)
            flow._choices = {series_key(SERIES): SERIES}
            for selected in ([], ["invalid"]):
                form = await flow.async_step_series({"series": selected, "add_another": False})
                self.assertEqual(form["errors"], {"series": "invalid_series"})

    async def test_removal_requires_explicit_confirmation_and_can_be_cancelled(self):
        flow = self.flow(True)
        result = await flow.async_step_remove({"series_to_remove": series_key(SERIES)})
        self.assertEqual(result["step_id"], "confirm_remove")
        self.assertIn("D\u00f8gn", result["description_placeholders"]["series"])
        self.assertEqual(flow._selected_series, [SERIES])
        result = await flow.async_step_confirm_remove({"confirm": False})
        self.assertEqual(result["step_id"], "init")
        self.assertEqual(flow._selected_series, [SERIES])
        await flow.async_step_remove({"series_to_remove": series_key(SERIES)})
        result = await flow.async_step_confirm_remove({"confirm": True})
        self.assertEqual(result["type"], FlowResultType.CREATE_ENTRY)
        self.assertEqual(result["data"]["series"], [])
        self.assertEqual(self.entry.options["series"], [SERIES])
