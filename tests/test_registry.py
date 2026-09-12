"""Use real registries to test removal and upgrades without touching history."""

import tempfile
from types import MappingProxyType
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.nve_hydapi.registry import async_cleanup_registry


class RegistryTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.hass = HomeAssistant(directory.name)
        self.hass.config_entries = Mock()
        self.entries = {}
        self.hass.config_entries.async_get_entry.side_effect = self.entries.get
        self.hass.config_entries.async_get_known_entry.side_effect = self.entries.__getitem__
        self.entry = self.make_entry("nve_hydapi")
        self.other = self.make_entry("another_integration")
        if hasattr(dr, "async_setup"):
            dr.async_setup(self.hass)
        await dr.async_load(self.hass)
        await er.async_load(self.hass)
        self.devices = dr.async_get(self.hass)
        self.entities = er.async_get(self.hass)

    def make_entry(self, domain):
        entry = ConfigEntry(
            version=1, minor_version=1, domain=domain, title=domain, source="user",
            data={"api_key": "test-key"}, options={"scan_interval": 15, "series": []},
            unique_id=domain, discovery_keys=MappingProxyType({}), subentries_data=None,
        )
        self.entries[entry.entry_id] = entry
        return entry

    def make_sensor(self, station, suffix="", disabled=False):
        device = self.devices.async_get_or_create(
            config_entry_id=self.entry.entry_id, identifiers={("nve_hydapi", station)}, name=station
        )
        entity = self.entities.async_get_or_create(
            "sensor", "nve_hydapi", f"nve_hydapi_{station}|1001|0|1{suffix}",
            config_entry=self.entry, device_id=device.id,
            disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
        )
        return device, entity

    async def test_last_series_removes_measurement_status_and_device(self):
        device, entity = self.make_sensor("1.2.0")
        _, status = self.make_sensor("1.2.0", "_status", disabled=True)
        async_cleanup_registry(self.hass, self.entry)
        self.assertIsNone(self.entities.async_get(entity.entity_id))
        self.assertIsNone(self.entities.async_get(status.entity_id))
        self.assertIsNone(self.devices.async_get(device.id))

    async def test_upgrade_keeps_selected_ids_names_and_disabled_preferences(self):
        selected = {"station_id": "1.2.0", "parameter": 1001, "resolution_time": "0", "version_number": 1}
        # Represents an unchanged 0.1.12 config entry loaded by the new version.
        object.__setattr__(self.entry, "options", MappingProxyType({"series": [selected]}))
        device, entity = self.make_sensor("1.2.0", disabled=True)
        self.entities.async_update_entity(entity.entity_id, name="My river")
        orphan_device, orphan = self.make_sensor("2.3.0")
        async_cleanup_registry(self.hass, self.entry)
        kept = self.entities.async_get(entity.entity_id)
        self.assertEqual(kept.name, "My river")
        self.assertEqual(kept.disabled_by, er.RegistryEntryDisabler.USER)
        self.assertEqual(kept.unique_id, entity.unique_id)
        self.assertIsNotNone(self.devices.async_get(device.id))
        self.assertIsNone(self.entities.async_get(orphan.entity_id))
        self.assertIsNone(self.devices.async_get(orphan_device.id))

    async def test_shared_device_and_other_integration_survive(self):
        device, entity = self.make_sensor("1.2.0")
        if hasattr(device, "config_entry_id"):
            other_device = self.devices.async_get_or_create(
                config_entry_id=self.other.entry_id, identifiers={("nve_hydapi", "1.2.0")}
            )
        else:
            other_device = self.devices.async_update_device(device.id, add_config_entry_id=self.other.entry_id)
        unrelated = self.entities.async_get_or_create(
            "sensor", "another_integration", "other-sensor", config_entry=self.other,
            device_id=other_device.id,
        )
        async_cleanup_registry(self.hass, self.entry)
        self.assertIsNone(self.entities.async_get(entity.entity_id))
        self.assertIsNotNone(self.entities.async_get(unrelated.entity_id))
        kept = self.devices.async_get(other_device.id)
        if hasattr(kept, "config_entry_id"):
            self.assertEqual(kept.config_entry_id, self.other.entry_id)
        else:
            self.assertEqual(kept.config_entries, {self.other.entry_id})
