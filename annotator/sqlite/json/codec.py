"""CODEX: Encode and decode JSON payload fields for SQLite bridges.

This module owns compact deterministic JSON serialization for values stored in
SQLite ``*_json`` columns and tolerant decoding for optional JSON payloads that
may be absent, blank, legacy-shaped, or manually corrupted.

Numeric coercion is limited to imported JSON metadata where a fallback is part
of the projection contract. Schema-owned SQLite text values should not be
runtime-stringified through this module.
"""

from __future__ import annotations

import json
from typing import Any


def _json_dumps(value: Any) -> str:
    """CODEX: Return compact, sorted JSON text for stored payload columns."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: Any, default: Any) -> Any:
    """CODEX: Decode optional JSON text, returning ``default`` when unusable.

    This helper is intentionally tolerant for backup, audit, geometry, and
    metadata payloads. It is not a schema validator and does not repair the
    stored value.
    """

    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _coerce_int(value: Any, default: int) -> int:
    """CODEX: Return an integer for loose JSON metadata or a fallback.

    Use this only where absent or malformed imported metadata has a documented
    fallback. Authoritative SQLite integer columns should generally use
    ``int(...)`` directly so schema problems surface naturally.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return default
