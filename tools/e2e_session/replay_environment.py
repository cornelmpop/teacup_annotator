"""CODEX: Inspect and enforce the authoritative GUI replay CI environment."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from collections.abc import Sequence
import json
import os
import platform
import sys
import tkinter as tk
from typing import Any


REQUIRED_REPLAY_ENVIRONMENT = (
    ("python_version", "3.12.13"),
    ("tcl_patch_level", "9.0.3"),
    ("tk_patch_level", "9.0.3"),
    ("windowing_system", "aqua"),
    ("platform_system", "Darwin"),
    ("platform_machine", "arm64"),
)


def collect_replay_environment(
    root: tk.Misc,
    runner_environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """CODEX: Read full Tk and runner metadata from an initialized Tk root.

    The returned mapping records the interpreter, Tcl/Tk display stack, screen,
    and GitHub runner identity used for one replay run. Callers own whether the
    facts are diagnostic only or must match the required CI profile.
    """

    environment = os.environ if runner_environment is None else runner_environment
    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "tcl_patch_level": root.tk.call("info", "patchlevel"),
        "tk_patch_level": root.tk.call("package", "provide", "Tk"),
        "windowing_system": root.tk.call("tk", "windowingsystem"),
        "tk_scaling": root.tk.call("tk", "scaling"),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "screen_width": root.winfo_screenwidth(),
        "screen_height": root.winfo_screenheight(),
        "screen_depth": root.winfo_screendepth(),
        "github_runner_os": environment.get("RUNNER_OS"),
        "github_runner_arch": environment.get("RUNNER_ARCH"),
        "github_runner_name": environment.get("RUNNER_NAME"),
        "github_runner_environment": environment.get("RUNNER_ENVIRONMENT"),
        "github_image_os": environment.get("ImageOS"),
        "github_image_version": environment.get("ImageVersion"),
    }


def required_environment_mismatches(
    environment: Mapping[str, Any],
) -> tuple[str, ...]:
    """CODEX: Return deviations from the required replay CI profile.

    Scaling and screen dimensions remain reported facts because the exact
    geometry and durable-state replay assertions own their compatibility.
    """

    mismatches = []
    for name, expected in REQUIRED_REPLAY_ENVIRONMENT:
        achieved = environment.get(name)
        if achieved != expected:
            mismatches.append(
                f"{name}: expected {expected!r}, achieved {achieved!r}"
            )
    return tuple(mismatches)


def main(arguments: Sequence[str] | None = None) -> None:
    """CODEX: Print replay metadata and optionally enforce the required CI profile.

    Tk initialization errors intentionally propagate because Tk owns display
    availability and CI must fail rather than translate or skip that failure.
    """

    parser = argparse.ArgumentParser(
        description="Report the GUI replay interpreter and Tk environment."
    )
    parser.add_argument(
        "--require-supported",
        action="store_true",
        help="fail unless the required authoritative replay CI profile is active",
    )
    options = parser.parse_args(arguments)

    root = tk.Tk()
    try:
        environment = collect_replay_environment(root)
    finally:
        root.destroy()

    print(json.dumps(environment, indent=2, sort_keys=True))
    mismatches = required_environment_mismatches(environment)
    if options.require_supported and mismatches:
        details = "; ".join(mismatches)
        raise SystemExit(f"required GUI replay environment mismatch: {details}")


if __name__ == "__main__":
    main()
