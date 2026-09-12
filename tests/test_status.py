"""Freshness, precision and translated entity metadata."""

from datetime import UTC, datetime, timedelta
from unittest import TestCase
from unittest.mock import Mock

from custom_components.nve_hydapi.observation import observation_status, observation_time
from custom_components.nve_hydapi.sensor import NveHydApiSensor, NveHydApiStatusSensor
from custom_components.nve_hydapi.api import series_key


class StatusTests(TestCase):
    def test_age_is_resolution_aware_and_not_a_quality_claim(self):
        now = datetime.now(UTC)
        item = {"value": 10, "time": (now - timedelta(hours=4)).isoformat(), "quality": 0}
        self.assertEqual(observation_status(item, "0", now)["data_status"], "stale")
        self.assertEqual(observation_status(item, "1440", now)["data_status"], "current")
        item["time"] = (now - timedelta(days=4)).isoformat()
        self.assertEqual(observation_status(item, "1440", now)["data_status"], "stale")

    def test_bad_values_times_and_future_dates_are_not_current(self):
        now = datetime.now(UTC)
        for value in (None, True, "12", float("nan"), float("inf")):
            self.assertEqual(observation_status({"value": value}, "0", now)["data_status"], "missing")
        for time in (None, "invalid", (now + timedelta(hours=1)).isoformat()):
            self.assertEqual(observation_status({"value": 12, "time": time}, "0", now)["data_status"], "invalid_time")
        self.assertEqual(observation_time("2026-09-12T12:00:00").tzinfo, UTC)

    def test_sensor_precision_and_status_metadata(self):
        for parameter, expected in ((1001, 12.35), (1000, 12.35), (1003, 12.3), (17, 12.3), (999, 12.35)):
            selected = {"station_id": "1.2.0", "parameter": parameter, "resolution_time": "1440"}
            coordinator = Mock()
            coordinator.data = {series_key(selected): {"value": 12.3456}}
            sensor = NveHydApiSensor(coordinator, selected)
            self.assertEqual(sensor.native_value, expected)
            self.assertEqual(sensor.translation_key, "daily")
            status = NveHydApiStatusSensor(coordinator, selected)
            self.assertEqual(status.translation_key, "status_daily")
            self.assertNotIn("_attr_name", status.__dict__)
            self.assertIsNone(status.native_unit_of_measurement)
            self.assertIsNone(status.state_class)
            self.assertEqual(status.native_value, "invalid_time")
