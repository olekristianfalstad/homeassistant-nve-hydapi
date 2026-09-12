"""Run an isolated Home Assistant with deterministic, non-networked HydAPI data."""

from datetime import UTC, datetime
import shutil
import sys
from pathlib import Path

config_dir, source = map(Path, sys.argv[1:3])
target = config_dir / "custom_components" / "nve_hydapi"
shutil.copytree(source / "custom_components" / "nve_hydapi", target, dirs_exist_ok=True)
config_dir.joinpath("configuration.yaml").write_text(
    "homeassistant:\n  name: HydAPI UI Test\n  latitude: 63.4\n  longitude: 10.4\n"
    "  elevation: 0\n  unit_system: metric\n  time_zone: Europe/Oslo\n  country: NO\n  language: nb\n"
    "http:\n  server_host: 127.0.0.1\n  server_port: 8123\n"
    "frontend:\napi:\nconfig:\nmy:\n", encoding="utf-8"
)
sys.path.insert(0, str(config_dir))
from custom_components.nve_hydapi.api import NveHydApiClient  # noqa: E402


async def fixture_request(self, method, path, *, params=None, json=None):
    if path == "/Stations":
        return {"data": [{"stationId": "139.15.0", "stationName": "Bj\u00f8rnstad", "councilName": "Namsskogan"}]}
    if path == "/Parameters":
        return {"data": [{"parameter": 1001}]}
    if path == "/Series":
        return {"data": [{"stationId": "139.15.0", "stationName": "Bj\u00f8rnstad",
                          "parameter": 1001, "parameterName": "Vannf\u00f8ring", "unit": "m\u00b3/s",
                          "versionNo": 1, "resolutionList": [{"resTime": r} for r in (0, 60, 1440)]}]}
    if path == "/Observations":
        return {"data": [{"stationId": item["stationId"], "parameter": int(item["parameter"]),
                          "serieVersionNo": 1, "observations": [{"value": 123.456,
                          "time": datetime.now(UTC).isoformat(), "quality": 1}]} for item in json]}
    raise AssertionError(f"Unexpected fixture request: {method} {path}")


NveHydApiClient._request = fixture_request
sys.argv = ["hass", "--config", str(config_dir)]
from homeassistant.__main__ import main  # noqa: E402

sys.exit(main())
