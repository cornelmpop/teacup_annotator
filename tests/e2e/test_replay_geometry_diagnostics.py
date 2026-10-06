"""CODEX: Verify exact replay geometry failures retain achieved dimensions."""

from __future__ import annotations

import pytest

from tools.e2e_session.replay_runtime import ReplayRuntime
from tools.e2e_session.session_format import SourceLocation


def test_wait_until_reports_expected_and_achieved_geometry() -> None:
    """CODEX: BUG-2026-10-04-GUI-REPLAY-CI-ENVIRONMENT reports both sizes."""

    runtime = object.__new__(ReplayRuntime)
    runtime.pump = lambda cycles=3: None
    runtime.raise_failures = lambda location: None

    with pytest.raises(AssertionError) as error:
        runtime.wait_until(
            lambda: False,
            SourceLocation("recording.session", 3),
            "expected initial canvas size (762, 642)",
            timeout_ms=0,
            timeout_details=lambda: "achieved (761, 641)",
        )

    assert str(error.value) == (
        "recording.session:3: timed out waiting for expected initial canvas size "
        "(762, 642); achieved (761, 641)"
    )
