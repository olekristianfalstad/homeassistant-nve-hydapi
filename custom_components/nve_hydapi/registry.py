"""Remove only registry objects no longer owned by selected HydAPI series."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .api import series_key
from .const import CONF_SERIES, DOMAIN


@callback
def async_cleanup_registry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reconcile saved selections, including stale entries from older versions."""
    selected = entry.options.get(CONF_SERIES, [])
    keep = {
        f"{DOMAIN}_{series_key(series)}{suffix}"
        for series in selected for suffix in ("", "_status")
    }
    entities = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entities, entry.entry_id):
        if (
            entity.platform == DOMAIN and entity.domain == "sensor"
            and entity.unique_id.startswith(f"{DOMAIN}_")
            and entity.unique_id not in keep
        ):
            entities.async_remove(entity.entity_id)

    stations = {(DOMAIN, str(series["station_id"])) for series in selected}
    devices = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(devices, entry.entry_id):
        if not any(domain == DOMAIN for domain, _ in device.identifiers):
            continue
        if device.identifiers & stations:
            continue
        if any(entity.config_entry_id == entry.entry_id for entity in
               er.async_entries_for_device(entities, device.id, include_disabled_entities=True)):
            continue
        # Detach only this integration; a shared device belongs to other entries too.
        devices.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
