"""Config flow for NVE HydAPI."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import NveHydApiAuthError, NveHydApiClient, NveHydApiError
from .const import (
    CONF_ADD_ANOTHER,
    CONF_CUSTOM_NAME,
    CONF_SCAN_INTERVAL,
    CONF_SERIES,
    CONF_SERIES_TO_REMOVE,
    CONF_STATION_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
    RESOLUTION_LABELS,
)

async def _load_active_station_options(
    hass: HomeAssistant, api_key: str
) -> dict[str, str]:
    """Validate the API key and return searchable active station options."""
    client = NveHydApiClient(async_get_clientsession(hass), api_key)
    return _build_station_options(await client.async_get_active_stations())


def _scan_interval_selector(default: int) -> NumberSelector:
    """Return scan interval selector."""
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL_MINUTES,
            max=1440,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="min",
        )
    )


def _series_option_label(series: dict[str, Any]) -> str:
    """Build a human readable label for one selected series."""
    resolution = RESOLUTION_LABELS.get(
        str(series["resolution_time"]), str(series["resolution_time"])
    )
    unit = f" ({series['unit']})" if series.get("unit") else ""
    version = ""
    if series.get("version_number") is not None:
        version = f", v{series['version_number']}"
    return (
        f"{series.get('station_name') or series['station_id']} "
        f"[{series['station_id']}] - {series.get('parameter_name') or series['parameter']}"
        f"{unit} - {resolution}{version}"
    )


def _station_option_label(station: dict[str, Any]) -> str:
    """Build a concise searchable label for a HydAPI station."""
    station_id = str(station["stationId"])
    label = f"{station.get('stationName') or station_id} [{station_id}]"
    location = station.get("councilName") or station.get("countyName")
    if location:
        label = f"{label} - {location}"
    return label


def _build_station_options(stations: list[dict[str, Any]]) -> dict[str, str]:
    """Convert HydAPI station metadata to sorted selector options."""
    options = {
        str(station["stationId"]): _station_option_label(station)
        for station in stations
        if station.get("stationId")
    }
    return dict(sorted(options.items(), key=lambda item: item[1].casefold()))


def _station_schema(options: dict[str, str]) -> vol.Schema:
    """Return a searchable station selector schema."""
    return vol.Schema(
        {
            vol.Required(CONF_STATION_ID): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": value, "label": label}
                        for value, label in options.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _build_choices(series_list: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Convert HydAPI series metadata to selectable choices."""
    choices: dict[str, dict[str, Any]] = {}
    for series in series_list:
        for resolution in series.get("resolutionList") or []:
            res_time = str(resolution.get("resTime"))
            version = series.get("versionNo")
            key = "|".join(
                [
                    str(series.get("stationId")),
                    str(series.get("parameter")),
                    res_time,
                    "" if version is None else str(version),
                ]
            )
            choices[key] = {
                "station_id": str(series.get("stationId")),
                "station_name": series.get("stationName"),
                "parameter": int(series.get("parameter")),
                "parameter_name": series.get("parameterName"),
                "unit": series.get("unit"),
                "resolution_time": res_time,
                "version_number": version,
            }
    return choices


def _select_schema(options: dict[str, str]) -> vol.Schema:
    """Return schema for choosing one or more HydAPI series."""
    return vol.Schema(
        {
            vol.Required(CONF_SERIES): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": value, "label": label}
                        for value, label in options.items()
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=True,
                )
            ),
            vol.Optional(CONF_CUSTOM_NAME): str,
            vol.Required(CONF_ADD_ANOTHER, default=False): bool,
        }
    )


def _selected_choice_keys(user_input: dict[str, Any]) -> list[str]:
    """Return selected choice keys as a list."""
    selected = user_input[CONF_SERIES]
    return [selected] if isinstance(selected, str) else list(selected)


def _series_identity(series: dict[str, Any]) -> tuple[str, int, str, Any]:
    """Return the fields that uniquely identify a HydAPI series."""
    return (
        str(series["station_id"]),
        int(series["parameter"]),
        str(series["resolution_time"]),
        series.get("version_number"),
    )


def _append_selected_choices(
    selected_series: list[dict[str, Any]],
    choices: dict[str, dict[str, Any]],
    choice_keys: list[str],
    custom_name: str,
) -> None:
    """Append selected choices without adding duplicate HydAPI series."""
    existing = {_series_identity(series) for series in selected_series}
    for choice_key in choice_keys:
        selected = dict(choices[choice_key])
        identity = _series_identity(selected)
        if identity in existing:
            continue
        if custom_name:
            selected[CONF_CUSTOM_NAME] = custom_name
        selected_series.append(selected)
        existing.add(identity)


def _continue_schema() -> vol.Schema:
    """Return schema for recovering from an unintended add-another choice."""
    return vol.Schema({vol.Required(CONF_ADD_ANOTHER, default=False): bool})


class NveHydApiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NVE HydAPI."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_key: str | None = None
        self._scan_interval = DEFAULT_SCAN_INTERVAL_MINUTES
        self._selected_series: list[dict[str, Any]] = []
        self._station_options: dict[str, str] = {}
        self._choices: dict[str, dict[str, Any]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return NveHydApiOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            self._scan_interval = int(user_input[CONF_SCAN_INTERVAL])
            try:
                self._station_options = await _load_active_station_options(
                    self.hass, self._api_key
                )
            except NveHydApiAuthError:
                errors["base"] = "invalid_auth"
            except NveHydApiError:
                errors["base"] = "cannot_connect"
            else:
                if not self._station_options:
                    errors["base"] = "no_stations"
                else:
                    return await self.async_step_station()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self._scan_interval,
                    ): _scan_interval_selector(self._scan_interval),
                }
            ),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Search for a station."""
        errors: dict[str, str] = {}

        if user_input is not None:
            assert self._api_key is not None
            station_id = str(user_input[CONF_STATION_ID])
            if station_id not in self._station_options:
                errors[CONF_STATION_ID] = "invalid_station"
                return self.async_show_form(
                    step_id="station",
                    data_schema=_station_schema(self._station_options),
                    errors=errors,
                )

            client = NveHydApiClient(async_get_clientsession(self.hass), self._api_key)
            try:
                series_list = await client.async_get_station_series(station_id)
            except NveHydApiAuthError:
                errors["base"] = "invalid_auth"
            except NveHydApiError:
                errors["base"] = "cannot_connect"
            else:
                self._choices = _build_choices(series_list)
                if not self._choices:
                    errors["base"] = "no_series"
                else:
                    return await self.async_step_series()

        return self.async_show_form(
            step_id="station",
            data_schema=_station_schema(self._station_options),
            errors=errors,
        )

    async def async_step_series(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select discovered HydAPI series."""
        errors: dict[str, str] = {}

        if user_input is not None:
            choice_keys = _selected_choice_keys(user_input)
            custom_name = (user_input.get(CONF_CUSTOM_NAME) or "").strip()
            if custom_name and len(choice_keys) > 1:
                errors[CONF_CUSTOM_NAME] = "custom_name_single_series"
            else:
                _append_selected_choices(
                    self._selected_series,
                    self._choices,
                    choice_keys,
                    custom_name,
                )

                if user_input[CONF_ADD_ANOTHER]:
                    return await self.async_step_continue()

                return self._create_entry()

        options = {key: _series_option_label(value) for key, value in self._choices.items()}
        return self.async_show_form(
            step_id="series",
            data_schema=_select_schema(options),
            errors=errors,
        )

    async def async_step_continue(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm whether another station should be added."""
        if user_input is not None:
            if user_input[CONF_ADD_ANOTHER]:
                self._choices = {}
                return await self.async_step_station()
            return self._create_entry()

        return self.async_show_form(
            step_id="continue",
            data_schema=_continue_schema(),
        )

    def _create_entry(self) -> config_entries.ConfigFlowResult:
        """Create the configured NVE HydAPI entry."""
        return self.async_create_entry(
            title="NVE HydAPI",
            data={CONF_API_KEY: self._api_key},
            options={
                CONF_SCAN_INTERVAL: self._scan_interval,
                CONF_SERIES: self._selected_series,
            },
        )


class NveHydApiOptionsFlow(config_entries.OptionsFlow):
    """Handle NVE HydAPI options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._scan_interval = int(
            config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        )
        self._selected_series = list(config_entry.options.get(CONF_SERIES, []))
        self._station_options: dict[str, str] = {}
        self._choices: dict[str, dict[str, Any]] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._scan_interval = int(user_input[CONF_SCAN_INTERVAL])
            action = user_input["action"]
            if action == "add":
                try:
                    self._station_options = await _load_active_station_options(
                        self.hass, self._config_entry.data[CONF_API_KEY]
                    )
                except NveHydApiAuthError:
                    errors["base"] = "invalid_auth"
                except NveHydApiError:
                    errors["base"] = "cannot_connect"
                else:
                    if not self._station_options:
                        errors["base"] = "no_stations"
                    else:
                        return await self.async_step_station()
            if action == "remove":
                return await self.async_step_remove()
            if action == "finish":
                return self._save_options()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self._scan_interval,
                    ): _scan_interval_selector(self._scan_interval),
                    vol.Required("action", default="finish"): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": "finish", "label": "Lagre"},
                                {"value": "add", "label": "Legg til serie"},
                                {"value": "remove", "label": "Fjern serie"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Search for a station in options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = str(user_input[CONF_STATION_ID])
            if station_id not in self._station_options:
                errors[CONF_STATION_ID] = "invalid_station"
                return self.async_show_form(
                    step_id="station",
                    data_schema=_station_schema(self._station_options),
                    errors=errors,
                )

            client = NveHydApiClient(
                async_get_clientsession(self.hass),
                self._config_entry.data[CONF_API_KEY],
            )
            try:
                series_list = await client.async_get_station_series(station_id)
            except NveHydApiAuthError:
                errors["base"] = "invalid_auth"
            except NveHydApiError:
                errors["base"] = "cannot_connect"
            else:
                self._choices = _build_choices(series_list)
                if not self._choices:
                    errors["base"] = "no_series"
                else:
                    return await self.async_step_series()

        return self.async_show_form(
            step_id="station",
            data_schema=_station_schema(self._station_options),
            errors=errors,
        )

    async def async_step_series(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Add selected series in options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            choice_keys = _selected_choice_keys(user_input)
            custom_name = (user_input.get(CONF_CUSTOM_NAME) or "").strip()
            if custom_name and len(choice_keys) > 1:
                errors[CONF_CUSTOM_NAME] = "custom_name_single_series"
            else:
                _append_selected_choices(
                    self._selected_series,
                    self._choices,
                    choice_keys,
                    custom_name,
                )
                if user_input[CONF_ADD_ANOTHER]:
                    return await self.async_step_continue()
                return self._save_options()

        options = {key: _series_option_label(value) for key, value in self._choices.items()}
        return self.async_show_form(
            step_id="series",
            data_schema=_select_schema(options),
            errors=errors,
        )

    async def async_step_continue(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm whether another station should be added."""
        if user_input is not None:
            if user_input[CONF_ADD_ANOTHER]:
                self._choices = {}
                return await self.async_step_station()
            return self._save_options()

        return self.async_show_form(
            step_id="continue",
            data_schema=_continue_schema(),
        )

    async def async_step_remove(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Remove one configured series."""
        if not self._selected_series:
            return self._save_options()

        if user_input is not None:
            index = int(user_input[CONF_SERIES_TO_REMOVE])
            self._selected_series.pop(index)
            return self._save_options()

        options = [
            {"value": str(index), "label": _series_option_label(series)}
            for index, series in enumerate(self._selected_series)
        ]
        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERIES_TO_REMOVE): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    def _save_options(self) -> config_entries.ConfigFlowResult:
        """Save options."""
        return self.async_create_entry(
            title="",
            data={
                CONF_SCAN_INTERVAL: self._scan_interval,
                CONF_SERIES: self._selected_series,
            },
        )
