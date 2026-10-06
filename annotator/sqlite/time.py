"""CODEX: Time helpers for Teacup-native SQLite rows."""

from __future__ import annotations


def _unix_time() -> int:
    """CODEX: Return integer Unix seconds for schema timestamp columns."""

    import time

    return int(time.time())


def _unix_time_ms() -> int:
    """CODEX: Return Unix milliseconds for audit and benchmark rows."""

    import time

    return time.time_ns() // 1_000_000
