"""Shared primitives for the hand-coded config validators.

A closed schema per plugin — never arbitrary JSON interpreted flexibly,
and never anything feeding a Python eval or attribute-path lookup — keeps
story-author config from becoming an injection surface. That risk is
separate from the EXTERNAL binding trust a host already gates, so a
validated shape is required whether or not the story is otherwise
trusted.

Each validator takes an already-decoded value (dict/list/str/int/float/
bool/None only) and either returns cleanly or raises
`SystemConfigValidationError` with a readable reason. None constructs an
object or imports a name by string; every check is a plain shape, type or
value comparison.

Hand-coded rather than depending on jsonschema: too few schemas so far to
justify the dependency, which becomes the better choice once one arrives
with real nested or conditional structure.

**The validators themselves live with the plugins they describe**, beside
the `initial_state()` that consumes the same config, so a shape and its
reader cannot drift apart. Only what more than one of them needs is here:
the error type and the scalar checks. A plugin points its own
`Plugin.validate_config` at its own validator, and a host that stores
config calls it.
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
            An empty name is rejected because every string this validates
            is an identifier or a label, and neither is meaningful blank.
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
            rejected rather than coerced, so a config says what it means.
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
            rejected explicitly: it is an int subclass in Python, and a
            `true` where a count belongs is a mistake worth catching.
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
