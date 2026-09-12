"""Sensor platform for NVE HydAPI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .api import series_key
from .const import (
    CONF_CUSTOM_NAME,
    CONF_SERIES,
    DOMAIN,
    INTEGRATION_URL,
    MANUFACTURER,
    RESOLUTION_TRANSLATION_KEYS,
    VALUE_PRECISION,
)
from .coordinator import NveHydApiCoordinator
from .observation import observation_status, valid_value

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NVE HydAPI sensors."""
    coordinator: NveHydApiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        entity(coordinator, series)
        for series in entry.options.get(CONF_SERIES, [])
        for entity in (NveHydApiSensor, NveHydApiStatusSensor)
    )


class NveHydApiSensor(CoordinatorEntity[NveHydApiCoordinator], SensorEntity):
    """Representation of a HydAPI observation sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: NveHydApiCoordinator,
        selected_series: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._series = selected_series
        self._key = series_key(selected_series)
        self._attr_unique_id = f"{DOMAIN}_{self._key}"
        self._precision = VALUE_PRECISION.get(int(selected_series["parameter"]), 2)
        self._attr_suggested_display_precision = self._precision
        if custom_name := selected_series.get(CONF_CUSTOM_NAME):
            self._attr_name = custom_name
        else:
            self._attr_translation_key = RESOLUTION_TRANSLATION_KEYS.get(
                str(selected_series["resolution_time"]), "instantaneous"
            )
            self._attr_translation_placeholders = {
                "parameter": selected_series.get("parameter_name") or str(selected_series["parameter"])
            }
        self._attr_native_unit_of_measurement = selected_series.get("unit")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, selected_series["station_id"])},
            manufacturer=MANUFACTURER,
            name=selected_series.get("station_name") or selected_series["station_id"],
            configuration_url=INTEGRATION_URL,
        )
        self._set_device_class_and_icon()

    @property
    def native_value(self) -> float | int | None:
        """Return the latest observed value."""
        item = self._coordinator_item
        if item is None:
            return None
        value = item.get("value")
        if not valid_value(value):
            return None
        return round(value, self._precision)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.has_series(self._series)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        item = self._coordinator_item or {}
        series = self._series
        attrs: dict[str, Any] = {
            "station_id": series["station_id"],
            "station_name": series.get("station_name"),
            "parameter": series["parameter"],
            "parameter_name": series.get("parameter_name"),
            "resolution_time": series["resolution_time"],
            "nve_license": "https://data.norge.no/nlod/no",
        }
        attrs.update(observation_status(item, str(series["resolution_time"]), dt_util.utcnow()))
        if self.coordinator.last_successful_update is not None:
            attrs["last_successful_update"] = self.coordinator.last_successful_update.isoformat()

        if series.get("version_number") is not None:
            attrs["version_number"] = series["version_number"]
        if item.get("time") is not None:
            attrs["observation_time"] = item["time"]
        if item.get("quality") is not None:
            attrs["quality"] = item["quality"]
        if item.get("correction") is not None:
            attrs["correction"] = item["correction"]

        return attrs

    @property
    def _coordinator_item(self) -> dict[str, Any] | None:
        """Return data for this sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)

    def _set_device_class_and_icon(self) -> None:
        """Set Home Assistant metadata based on parameter/unit."""
        parameter = int(self._series["parameter"])
        unit = self._series.get("unit")
        parameter_name = (self._series.get("parameter_name") or "").lower()

        if unit in (UnitOfTemperature.CELSIUS, "\u00b0C", "C") or "temperatur" in parameter_name:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

        if parameter == 1003:
            self._attr_icon = "mdi:thermometer-water"
        elif parameter == 17:
            self._attr_icon = "mdi:thermometer"
        elif parameter == 1000:
            self._attr_icon = "mdi:waves"
        elif parameter == 1001:
            self._attr_icon = "mdi:water"
        else:
            self._attr_icon = "mdi:chart-line"


class NveHydApiStatusSensor(NveHydApiSensor):
    """A visible diagnostic state separate from the measurement's availability."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = None
    _attr_options = ["current", "stale", "missing", "invalid_time"]

    def __init__(self, coordinator: NveHydApiCoordinator, selected_series: dict[str, Any]) -> None:
        super().__init__(coordinator, selected_series)
        self._attr_unique_id = f"{DOMAIN}_{self._key}_status"
        self.__dict__.pop("_attr_name", None)
        resolution = RESOLUTION_TRANSLATION_KEYS.get(str(selected_series["resolution_time"]), "instantaneous")
        self._attr_translation_key = f"status_{resolution}"
        self._attr_translation_placeholders = {
            "parameter": selected_series.get(CONF_CUSTOM_NAME)
            or selected_series.get("parameter_name") or str(selected_series["parameter"])
        }
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_native_unit_of_measurement = None
        self._attr_suggested_display_precision = None
        self._attr_icon = "mdi:database-clock"

    @property
    def native_value(self) -> str:
        return observation_status(
            self._coordinator_item or {}, str(self._series["resolution_time"]), dt_util.utcnow()
        )["data_status"]

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
