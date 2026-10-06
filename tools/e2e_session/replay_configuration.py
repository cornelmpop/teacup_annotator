"""CODEX: Replay Configuration-window choices and complete Save inputs.

The session owns portable editor input values. Replay restores fixture or
preflighted model-asset paths into the live editor and invokes its actual
chooser or Save callback, leaving field validation, project metadata,
preferences, model configuration, and runtime refresh effects with production.
"""

from __future__ import annotations

from typing import Any

from tools.e2e_session.model_assets import resolve_file_token
from tools.e2e_session.replay_setup import ReplaySetup
from tools.e2e_session.session_format import SessionEntry


def replay_configuration_choose(app: Any, entry: SessionEntry) -> None:
    """CODEX: Invoke the recorded chooser on the live Configuration editor."""

    editor = _configuration_editor(app, entry)
    if entry.arguments == ("model_profile",):
        editor.choose_model_profile()
        return
    if entry.arguments == ("model_weights",):
        editor.choose_model_weights()
        return
    if len(entry.arguments) == 2 and entry.arguments[0] == "colour":
        key = entry.arguments[1]
        if key not in editor.COLOUR_KEYS:
            raise AssertionError(
                f"{entry.location}: unknown Configuration colour key {key!r}"
            )
        editor.choose_colour(key)
        return
    raise AssertionError(
        f"{entry.location}: config_choose requires model_profile, "
        "model_weights, or colour KEY"
    )


def replay_configuration_save(
    app: Any,
    setup: ReplaySetup,
    entry: SessionEntry,
) -> None:
    """CODEX: Restore complete editor fields and invoke the real Save effect.

    Exact key equality is intentional: a recording is tied to the editor
    contract that produced it. Missing or newly added fields must be reviewed
    and re-recorded instead of silently inheriting local defaults. Model
    weights resolve from either the copied fixture or replay's verified local
    asset registry.
    """

    editor = _configuration_editor(app, entry)
    values = _configuration_values(entry)
    expected_keys = (
        set(editor.vars)
        | set(editor.bool_vars)
        | set(editor.project_text_widgets)
    )
    actual_keys = set(values)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise AssertionError(
            f"{entry.location}: config_save field set differs; "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )

    normalized_values = dict(values)
    model_weights = normalized_values.get("model_weights", "")
    if model_weights:
        try:
            resolved = resolve_file_token(
                model_weights,
                setup.project_folder,
                setup.model_assets,
            )
        except ValueError as exc:
            raise AssertionError(f"{entry.location}: {exc}") from exc
        # CODEX: Tk StringVar owns text, so convert the authoritative Path at
        # CODEX: the GUI field boundary rather than in intermediary logic.
        normalized_values["model_weights"] = str(resolved)
    for key in editor.bool_vars:
        value = values[key]
        if value not in {"true", "false"}:
            raise AssertionError(
                f"{entry.location}: Configuration boolean {key!r} "
                "must be true/false"
            )

    for key, variable in editor.vars.items():
        variable.set(normalized_values[key])
    for key, variable in editor.bool_vars.items():
        variable.set(normalized_values[key] == "true")
    for key, text_widget in editor.project_text_widgets.items():
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", values[key])

    editor.save()


def _configuration_editor(app: Any, entry: SessionEntry) -> Any:
    """CODEX: Return the open Configuration editor required by an action."""

    editor = app.configuration_window
    if editor is None:
        raise AssertionError(f"{entry.location}: Configuration window is not open")
    return editor


def _configuration_values(entry: SessionEntry) -> dict[str, str]:
    """CODEX: Parse unique Configuration ``key=value`` action arguments."""

    values: dict[str, str] = {}
    for token in entry.arguments:
        key, separator, value = token.partition("=")
        if separator != "=" or not key:
            raise AssertionError(
                f"{entry.location}: config_save requires key=value fields"
            )
        if key in values:
            raise AssertionError(
                f"{entry.location}: duplicate Configuration field {key!r}"
            )
        values[key] = value
    return values
