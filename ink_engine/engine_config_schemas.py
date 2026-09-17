"""Shared primitives for the hand-coded config validators.

A closed schema per plugin, validated whether or not the story is
otherwise trusted: story-author config must never become an injection
surface.

Each validator takes an already-decoded value (dict/list/str/int/float/
bool/None only) and either returns cleanly or raises
`SystemConfigValidationError` with a readable reason. **No validator ever
constructs an object or imports a name by string**; every check is a
plain shape, type or value comparison.

**The validators themselves live with the plugins they describe.** Only
what more than one of them needs is here: the error type and the scalar
checks. A plugin points its own `Plugin.validate_config` at its own
validator, and an application that stores config calls it.
"""

from __future__ import annotations

from typing import Any


class SystemConfigValidationError(ValueError):
    """Raised when a plugin's config JSON doesn't match its
    system_name's closed schema."""


def require_dict(value: Any, path: str) -> dict[str, Any]:
    """Return `value` if it is a dict, else raise.

    Args:
        value: The value to check.
        path: Dotted config path, for the error message.

    Returns:
        The value, unchanged.

    Raises:
        SystemConfigValidationError: If it is not a dict.
    """
    if not isinstance(value, dict):
        raise SystemConfigValidationError(f"{path} must be an object, got {type(value).__name__}")
    return value


def require_str(value: Any, path: str) -> str:
    """Return `value` if it is a non-empty string, else raise.

    Args:
        value: The value to check.
        path: Dotted config path, for the error message.

    Returns:
        The value, unchanged.

    Raises:
        SystemConfigValidationError: If it is not a string, or is empty.
    """
    if not isinstance(value, str) or not value:
        raise SystemConfigValidationError(f"{path} must be a non-empty string")
    return value


def require_bool(value: Any, path: str) -> bool:
    """Return `value` if it is a real bool, else raise.

    Args:
        value: The value to check.
        path: Dotted config path, for the error message.

    Returns:
        The value, unchanged.

    Raises:
        SystemConfigValidationError: If it is not a bool. A 0 or 1 is
            rejected, never coerced.
    """
    if not isinstance(value, bool):
        raise SystemConfigValidationError(f"{path} must be a boolean")
    return value


def require_int(value: Any, path: str) -> int:
    """Return `value` if it is a real int, else raise.

    Args:
        value: The value to check.
        path: Dotted config path, for the error message.

    Returns:
        The value, unchanged.

    Raises:
        SystemConfigValidationError: If it is not an int. `bool` is
            rejected explicitly, being an int subclass in Python.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemConfigValidationError(f"{path} must be an integer")
    return value


def require_number(value: Any, path: str) -> float:
    """Return `value` if it is a real number, else raise.

    Args:
        value: The value to check.
        path: Dotted config path, for the error message.

    Returns:
        The value, unchanged.

    Raises:
        SystemConfigValidationError: If it is not an int or float. `bool`
            is rejected explicitly, being an int subclass in Python.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SystemConfigValidationError(f"{path} must be a number")
    return value


# The helpers above are shared by more than one plugin's own validator.
# A check only one plugin needs lives with that plugin.
