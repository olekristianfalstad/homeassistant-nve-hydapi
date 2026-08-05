"""Constants for the NVE HydAPI integration."""

from datetime import timedelta

DOMAIN = "nve_hydapi"

CONF_ADD_ANOTHER = "add_another"
CONF_CUSTOM_NAME = "custom_name"
CONF_REFERENCE_TIME = "reference_time"
CONF_RESOLUTION_TIME = "resolution_time"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SERIES = "series"
CONF_SERIES_TO_REMOVE = "series_to_remove"
CONF_STATION_ID = "station_id"

DEFAULT_SCAN_INTERVAL_MINUTES = 15
MIN_SCAN_INTERVAL_MINUTES = 10
DEFAULT_SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL_MINUTES)

HYDAPI_BASE_URL = "https://hydapi.nve.no/api/v1"
INTEGRATION_URL = "https://github.com/olekristianfalstad/"
MANUFACTURER = "NVE"

RESOLUTION_LABELS = {
    "0": "Momentan",
    "60": "Time",
    "1440": "Dogn",
}
