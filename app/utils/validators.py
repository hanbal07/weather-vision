"""Defensive validation helpers for untrusted API payloads.

The Open-Meteo responses are JSON from the internet: they may be missing
fields, contain ``None`` values, or use unexpected types. Every accessor
here walks a nested structure with a key chain and returns a safe default
instead of raising.
"""
from __future__ import annotations

from typing import Any


def _lookup(data: Any, keys: tuple) -> Any:
    """Walk nested dicts/lists following ``keys``.

    Strings select dict keys, integers index lists. Returns None when a step
    does not exist.
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, (list, tuple)) and isinstance(key, int):
            if not (-len(current) <= key < len(current)):
                return None
            current = current[key]
        else:
            return None
    return current


def fval(data: Any, *keys: Any, default: float | None = None) -> float | None:
    """Fetch a float value safely."""
    value = _lookup(data, keys)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ival(data: Any, *keys: Any, default: int | None = None) -> int | None:
    """Fetch an integer value safely."""
    value = _lookup(data, keys)
    if value is None:
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def sval(data: Any, *keys: Any, default: str = "") -> str:
    """Fetch a non-empty string safely."""
    value = _lookup(data, keys)
    if isinstance(value, str) and value:
        return value
    return default


def require_keys(data: Any, *keys: Any) -> None:
    """Raise ValueError if a required field chain is missing entirely."""
    if _lookup(data, keys) is None:
        raise ValueError(f"Missing required field: {keys}")
