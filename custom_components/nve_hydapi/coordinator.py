"""Coordinator for NVE HydAPI."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NveHydApiClient, NveHydApiError, series_key
from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SERIES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class NveHydApiCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch all configured HydAPI series in one coordinated poll."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: NveHydApiClient,
    ) -> None:
        """Initialize the coordinator."""
        self.entry = entry
        self.client = client
        minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES))

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
            always_update=False,
        )

    @property
    def selected_series(self) -> list[dict[str, Any]]:
        """Return selected HydAPI series from options."""
        return list(self.entry.options.get(CONF_SERIES, []))

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from HydAPI."""
        try:
            return await self.client.async_fetch_observations(self.selected_series)
        except NveHydApiError as err:
            raise UpdateFailed(str(err)) from err

    def has_series(self, item: dict[str, Any]) -> bool:
        """Return if coordinator data has this series."""
        return series_key(item) in (self.data or {})
