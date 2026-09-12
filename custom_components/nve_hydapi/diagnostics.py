"""Diagnostics support for NVE HydAPI."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.redact import async_redact_data
from .const import DOMAIN

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    return async_redact_data(
        {
            "data": config_entry.data,
            "options": config_entry.options,
            "last_update_success": coordinator.last_update_success if coordinator else None,
            "last_successful_update": (
                coordinator.last_successful_update.isoformat()
                if coordinator and coordinator.last_successful_update else None
            ),
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    return await async_get_config_entry_diagnostics(hass, config_entry)
