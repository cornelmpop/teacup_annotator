"""Provide the installed launcher for the GUI-only Teacup Annotator app.

The project still uses a command-line entry point so launching from a terminal
preserves stdout/stderr for tracebacks, dependency import errors, and other
diagnostics that may happen before the GUI can show an error dialog. The same
entry point also exposes lightweight packaging smoke checks. The GUI application
is imported lazily so `--version` and `--check-resources` can run without
initializing Tk.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from annotator.resources import check_packaged_resources
from annotator.release_identity import APP_NAME
from annotator.release_identity import APP_VERSION


def build_parser() -> argparse.ArgumentParser:
    """Create the parser for installed command-line smoke checks.

    The command intentionally exposes only startup-safe package checks; normal
    annotation work remains owned by the GUI application entry point.
    """

    parser = argparse.ArgumentParser(prog="teacup-annotator")
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the application version and exit",
    )
    parser.add_argument(
        "--check-resources",
        action="store_true",
        help="verify packaged schema, preference defaults, and icons",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a launcher action and return a process exit status.

    `argv` is injectable so tests can exercise the installed launcher without
    patching `sys.argv`. With no smoke-check option, control passes to the Tk
    GUI while keeping terminal output attached for uncaught startup failures.
    """

    args = build_parser().parse_args(argv)
    if args.version:
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if args.check_resources:
        check_packaged_resources()
        print("Packaged resources are readable.")
        return 0

    # Keep Tk imports out of smoke-check paths while preserving this command as
    # the normal GUI launcher with terminal diagnostics attached.
    from annotator.gui.application import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
