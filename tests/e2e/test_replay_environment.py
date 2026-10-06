"""CODEX: Verify the declared authoritative replay environment boundary."""

from __future__ import annotations

import json

import pytest

from tools.e2e_session import replay_environment


VERIFIED_ENVIRONMENT = {
    "python_version": "3.12.13",
    "python_implementation": "CPython",
    "python_executable": "/managed/python3.12",
    "tcl_patch_level": "9.0.3",
    "tk_patch_level": "9.0.3",
    "windowing_system": "aqua",
    "tk_scaling": 1.3339898243886428,
    "platform_system": "Darwin",
    "platform_release": "25.6.0",
    "platform_machine": "arm64",
    "screen_width": 1920,
    "screen_height": 1080,
    "screen_depth": 32,
    "github_runner_os": "macOS",
    "github_runner_arch": "ARM64",
    "github_runner_name": "GitHub Actions 1",
    "github_runner_environment": "github-hosted",
    "github_image_os": "macos15",
    "github_image_version": "20261001.1",
}


class _FakeTcl:
    """CODEX: Return deterministic Tcl/Tk metadata for the collection test."""

    def call(self, *arguments: str) -> str | float:
        """CODEX: Return the known Tcl result for one metadata query."""

        results = {
            ("info", "patchlevel"): "9.0.3",
            ("package", "provide", "Tk"): "9.0.3",
            ("tk", "windowingsystem"): "aqua",
            ("tk", "scaling"): 1.3339898243886428,
        }
        return results[arguments]


class _FakeRoot:
    """CODEX: Expose the Tk screen methods used by environment collection."""

    tk = _FakeTcl()

    def winfo_screenwidth(self) -> int:
        """CODEX: Return a fixed screen width for the metadata contract."""

        return 1920

    def winfo_screenheight(self) -> int:
        """CODEX: Return a fixed screen height for the metadata contract."""

        return 1080

    def winfo_screendepth(self) -> int:
        """CODEX: Return a fixed screen depth for the metadata contract."""

        return 32


def test_required_replay_profile_accepts_verified_tk9_aqua_environment() -> None:
    """CODEX: BUG-2026-10-04-GUI-REPLAY-CI-ENVIRONMENT accepts verified facts."""

    mismatches = replay_environment.required_environment_mismatches(
        VERIFIED_ENVIRONMENT
    )

    assert mismatches == ()


def test_required_replay_profile_reports_each_mismatch() -> None:
    """CODEX: BUG-2026-10-04-GUI-REPLAY-CI-ENVIRONMENT reports exact drift."""

    environment = VERIFIED_ENVIRONMENT | {
        "python_version": "3.12.12",
        "tk_patch_level": "8.6.14",
        "windowing_system": "x11",
        "platform_system": "Linux",
        "platform_machine": "x86_64",
    }

    mismatches = replay_environment.required_environment_mismatches(environment)

    assert mismatches == (
        "python_version: expected '3.12.13', achieved '3.12.12'",
        "tk_patch_level: expected '9.0.3', achieved '8.6.14'",
        "windowing_system: expected 'aqua', achieved 'x11'",
        "platform_system: expected 'Darwin', achieved 'Linux'",
        "platform_machine: expected 'arm64', achieved 'x86_64'",
    )


def test_collect_replay_environment_reports_full_runtime_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CODEX: BUG-2026-10-04-GUI-REPLAY-CI-ENVIRONMENT preserves diagnostics."""

    monkeypatch.setattr(replay_environment.platform, "python_version", lambda: "3.12.13")
    monkeypatch.setattr(
        replay_environment.platform,
        "python_implementation",
        lambda: "CPython",
    )
    monkeypatch.setattr(replay_environment.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(replay_environment.platform, "release", lambda: "25.6.0")
    monkeypatch.setattr(replay_environment.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(replay_environment.sys, "executable", "/managed/python3.12")
    runner_environment = {
        "RUNNER_OS": "macOS",
        "RUNNER_ARCH": "ARM64",
        "RUNNER_NAME": "GitHub Actions 1",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "ImageOS": "macos15",
        "ImageVersion": "20261001.1",
    }

    environment = replay_environment.collect_replay_environment(
        _FakeRoot(),
        runner_environment,
    )

    assert environment == VERIFIED_ENVIRONMENT


def test_environment_cli_prints_metadata_and_rejects_wrong_required_profile(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CODEX: BUG-2026-10-04-GUI-REPLAY-CI-ENVIRONMENT makes CI drift fatal."""

    environment = VERIFIED_ENVIRONMENT | {"tk_patch_level": "8.6.14"}
    destroyed = False

    class FakeCliRoot:
        """CODEX: Record that the environment CLI releases its Tk root."""

        def destroy(self) -> None:
            """CODEX: Record deterministic root cleanup after inspection."""

            nonlocal destroyed
            destroyed = True

    monkeypatch.setattr(replay_environment.tk, "Tk", FakeCliRoot)
    monkeypatch.setattr(
        replay_environment,
        "collect_replay_environment",
        lambda root: environment,
    )

    with pytest.raises(SystemExit) as error:
        replay_environment.main(["--require-supported"])

    report = json.loads(capsys.readouterr().out)
    assert report == environment
    assert str(error.value) == (
        "required GUI replay environment mismatch: "
        "tk_patch_level: expected '9.0.3', achieved '8.6.14'"
    )
    assert destroyed is True
