"""Conversions for the values the Anker library reports.

The library doesn't always convert numbers (some come as strings like "12.5")
and reports weekdays either as a bitmask or as a list of day names.
"""

from __future__ import annotations

from typing import Any, Final

WEEKDAYS: Final = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def to_number(value: Any) -> float | None:
    """Convert a reported value (int, float or numeric string) to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> int | None:
    """Convert a reported value (int, float or numeric string) to a whole number."""
    number = to_number(value)
    return None if number is None else round(number)


def is_on(value: Any) -> bool | None:
    """Whether a reported 0/1 flag is on (None if not reported)."""
    number = to_number(value)
    return None if number is None else number == 1


def to_weekdays(value: Any) -> list[str] | None:
    """Weekdays from the charger's bitmask (bit 0 = Monday) or the library's list."""
    if isinstance(value, list | tuple | set):
        return [day for day in WEEKDAYS if day in value]
    if (mask := to_int(value)) is None:
        return None
    return [day for idx, day in enumerate(WEEKDAYS) if mask & (1 << idx)]
