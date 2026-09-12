"""Interpret observation age without confusing it with API availability."""

from datetime import UTC, datetime
from math import isfinite
from typing import Any


def observation_time(value: Any) -> datetime | None:
    """HydAPI timestamps are UTC, including timestamps without an offset."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def valid_value(value: Any) -> bool:
    """Reject booleans, NaN and infinities as measurements."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def observation_status(item: dict[str, Any], resolution: str, now: datetime) -> dict[str, Any]:
    """Use a documented freshness heuristic, not an NVE quality classification."""
    try:
        stale_after = max(180, 3 * int(resolution))
    except (ValueError, TypeError):
        stale_after = 180
    observed = observation_time(item.get("time"))
    age = (now - observed).total_seconds() / 60 if observed else None
    if not valid_value(item.get("value")):
        status = "missing"
    elif age is None or age < -5:
        status = "invalid_time"
    elif age > stale_after:
        status = "stale"
    else:
        status = "current"
    return {
        "data_status": status,
        "observation_age_minutes": round(age, 1) if age is not None else None,
        "stale_after_minutes": stale_after,
    }
