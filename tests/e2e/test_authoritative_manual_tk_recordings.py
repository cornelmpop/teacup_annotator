"""CODEX: Replay and integrity-check protected human-recorded Tk evidence.

CODEX: Scenario-specific fixture preparation reproduces the declared starting
CODEX: state without changing the immutable session bytes.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import zipfile

from annotator.project.paths import project_file_path
from annotator.sqlite.constants import DATABASE_FILENAME
from tools.e2e_session import parse_session_file
from tools.e2e_session import replay_session
from tools.e2e_session.canonical_artifacts import canonical_artifact_file
from tools.e2e_session.canonical_outputs import Canonicalizer
from tools.e2e_session.session_format import SessionDocument


EVIDENCE_ROOT = Path(__file__).resolve().parent / "authoritative_manual_tk"
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
VIEWPORT_RECORDED_FOLDER = (
    "/private/tmp/teacup-gui-path-viewport-controls-20260830-a/recorded_project"
)
VIEWPORT_DERIVED_SCENARIOS = frozenset(
    {
        "archive_class_definitions_preflight",
        "archive_success",
        "reconcile_added_image_accept",
        "reconcile_added_image_reject",
        "reconcile_missing_image_accept",
    }
)
MANIFEST_SHA256 = {
    "annotation_delete_with_selected_vertices": (
        "8f563dd9a4b3cdf3601cc6ba6e6529757a3cfe4d956b123a7db5ad5a65cfba5c"
    ),
    "archive_class_definitions_preflight": (
        "f3112504de97f2bfe45af4d39c7ef15a0afe7c2340dd51037235002256ff648e"
    ),
    "archive_success": (
        "1b0d4fb42fa7c6f6574b41389c7670d286745ff6989e9939eb2cb8cd1cd2c147"
    ),
    "arrow_crossing_secondary_edits_preserve_polygon": (
        "4d98ed446da04353e8479be49c733d4faaacbed245cccac5a99db2f1b47b0003"
    ),
    "class_panel_lifecycle": (
        "002c6b863df8045e22b44b88655b7912a2e05a4ecf899c50f91a5fbcfa0aa1d6"
    ),
    "close_incomplete_arrow": (
        "d22e8dcb64deb87d737c1ec6fc04c9b98274ccd49e3983f723fbd018345287fa"
    ),
    "close_incomplete_polygon": (
        "296706fef43abbfbc4eab0aaa24026b38e48651233125e2bd5bd2638a019e61f"
    ),
    "completed_arrow_lifecycle": (
        "acd931a0fe5b8ad245ca8e598e28e295d06383b3e45f17660c0e085ff4bb1f03"
    ),
    "configuration_round_trip": (
        "ff63dd1786b015c9ff7b4c750979a115beeb434fbf3879a673fa8d89341cc15b"
    ),
    "delete_restore_save_confirmation": (
        "08b59600780436e1ec584258cf69d22d7159b52044585ab384b9310aff1655ca"
    ),
    "drawing_shortcuts_from_non_canvas_controls": (
        "499b8afeaa7ffecfb3f663c887f044974f5fba791534d6970d411a68d3a7e65b"
    ),
    "held_rectangle_key_repeat": (
        "603eb9200cbb9b75ae8d45978e1bb00e28a1036858d07e34291c477dcaba5333"
    ),
    "held_vertex_delete_navigation": (
        "e8583a8153d46d7b24505eef09a373df645740dd2be7c08c9779b439f6e1dfb3"
    ),
    "individual_vertex_insert_move_delete": (
        "3f0fdad7bb54039734b2203b45ae19015e831f8fc8a19bc61a91ed1f9d23bb1c"
    ),
    "interleaved_shortcuts": (
        "39c48d5979b9a832a16192b4dc5600e5dec271de90e6aba01c2f8806135e0e64"
    ),
    "menu_pointer_resize_causality": (
        "56c7a84a684863ae32239d616a9d3e03a8567aad1e3b01a03a7412381d036bea"
    ),
    "model_configuration_failure": (
        "2b3b27a192f7c8394a746bfcc747c450817a17cbc70eeecc20f637beac4ce208"
    ),
    "navigation_filter_review": (
        "29c93db81c150bf2e1f3bf5bad8d0585d94687df090f6b721a47f53803a77d88"
    ),
    "overlap_delete_undo_merge_reclassify": (
        "22d9e5bc93c1d6b4a661fc7524dcd358f229b19ee202b707ac83121bbdbd4dfd"
    ),
    "polygon_edit_reclassify_resample": (
        "ad3cdd95cbf73e074e79edc713afedcc97bb5ea677227f5da19f51a6af124bc4"
    ),
    "raw_keyboard_navigation_zoom_review_resample": (
        "afbddba8ca02d45463a309c7624e029e4eaeb6ab3e2fc915c086b3068217b783"
    ),
    "reconcile_added_image_accept": (
        "15944f84a08f88e3109e1bc39b08dd70a7d13d95e10d330c286deeb60ca1dc47"
    ),
    "reconcile_added_image_reject": (
        "77bfe931beac1c2589df73b7095bf2af5c754e4a5062e9ed10c2a233216dff15"
    ),
    "reconcile_missing_image_accept": (
        "cf9e757f06984ff6e4dd5af25e5a93bed660742fabae9a59a28d601a4f582701"
    ),
    "startup_cancel_toolbar_load": (
        "3dc80855298d8192db27101dda374d4167b62939e9d4792e72c699e7e5148ec8"
    ),
    "turtle_shell_shared_vertex": (
        "c0e362a7930b4d44d7790fcbd926804b596da634775261728df5d17c0de1c442"
    ),
    "viewport_overlay_controls": (
        "78e6ff38a670674a7462a9f4a067ae25ade34107c302808643874f641fd0b4cd"
    ),
}


def _sha256(path: Path) -> str:
    """CODEX: Return the SHA-256 digest of an evidence or replay artifact."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_manifest(bundle: Path) -> None:
    """CODEX: Verify the protected manifest and every artifact it names."""

    manifest_path = bundle / "MANIFEST.sha256"
    assert _sha256(manifest_path) == MANIFEST_SHA256[bundle.name]

    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        expected_digest, relative_name = line.split("  ", maxsplit=1)
        assert _sha256(bundle / relative_name) == expected_digest


def _normalized_action_order(document: SessionDocument) -> list[list[str]]:
    """CODEX: Return reviewable action order without incidental coordinates.

    Pointer coordinates remain protected by the session hash. Hover actions
    are retained as raw evidence but excluded because pointer travel is not a
    step in the human action sheets.
    """

    order = []
    for entry in document.actions:
        if entry.verb == "hover":
            continue
        if entry.verb == "dialog":
            signature = [*entry.tokens, "->", *entry.observations]
        elif entry.verb in {"click", "drag"}:
            signature = [entry.verb, *entry.arguments[:3]]
        elif entry.verb == "arrow_point":
            signature = [entry.verb, *entry.arguments[:2]]
        else:
            signature = [entry.verb, *entry.arguments]
        order.append(signature)
    return order


def _portable_document(
    session_path: Path,
    fixture_name: str = "master_2",
) -> SessionDocument:
    """CODEX: Rebind the fixture and supply the approved current config default."""

    document = parse_session_file(session_path)
    fixture_entry = next(entry for entry in document.setup if entry.verb == "fixture")
    # CODEX: Preserve recorded session bytes; only the parsed fixture locator is
    # CODEX: rebound for portable replay.
    portable_fixture = replace(fixture_entry, arguments=(fixture_name,))
    portable_setup = tuple(
        portable_fixture if entry is fixture_entry else entry
        for entry in document.setup
    )
    portable_document = replace(document, setup=portable_setup)
    if session_path.parent.name != "configuration_round_trip":
        return portable_document

    # CODEX: Supply the current schema's authoritative default without changing
    # CODEX: the protected recording or the human action order.
    portable_actions = tuple(
        replace(entry, arguments=(*entry.arguments, "crop_padding_px=20"))
        if entry.verb == "config_save"
        else entry
        for entry in document.actions
    )
    return replace(portable_document, actions=portable_actions)


def _assert_trace_has_no_synthesized_actions(trace_path: Path) -> None:
    """CODEX: Prove the evidence trace contains no recovery-made actions."""

    for line in trace_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        # CODEX: Audit/state recovery must remain diagnostic rather than create
        # CODEX: authoritative input.
        assert event["kind"] != "synthesized_action"


def _canonical_artifact_sha256(project_folder: Path) -> str:
    """CODEX: Hash the full canonical durable state of a replayed project."""

    database_path = project_file_path(project_folder, DATABASE_FILENAME)
    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        canonicalizer = Canonicalizer(project_folder)
        artifact_text = canonical_artifact_file(
            project_folder,
            connection,
            canonicalizer.value,
        )
    finally:
        connection.close()
    return hashlib.sha256(artifact_text.encode("utf-8")).hexdigest()


def _assert_archive_output(bundle: Path, project_folder: Path) -> None:
    """CODEX: Compare the replayed distribution ZIP with its approved Golden."""

    expected = json.loads(
        (bundle / "archive-output.json").read_text(encoding="utf-8")
    )
    archive_path = project_folder / "manual_archive.zip"
    with zipfile.ZipFile(archive_path) as archive:
        members = set(archive.namelist())
        assert members == set(expected["members"])

        annotations = json.loads(archive.read("annotations.json"))
        assert len(annotations["images"]) == expected["image_count"]
        assert len(annotations["annotations"]) == expected["annotation_count"]

        checksum_lines = archive.read("checksums.txt").decode("utf-8").splitlines()
        recorded_checksums = {
            line.split("  ", maxsplit=1)[1]: line.split("  ", maxsplit=1)[0]
            for line in checksum_lines
        }
        assert recorded_checksums.keys() == members - {"checksums.txt"}
        for member, expected_digest in recorded_checksums.items():
            assert hashlib.sha256(archive.read(member)).hexdigest() == expected_digest


def _replay_authoritative_recording(
    scenario: str,
    fixture_base: Path,
    fixture_name: str,
    project_folder: Path,
) -> Path:
    """CODEX: Verify and replay one bundle against its prepared fixture state."""

    bundle = EVIDENCE_ROOT / scenario
    session_path = bundle / f"authoritative_manual_tk__{scenario}.session"
    _assert_manifest(bundle)
    session_digest_before = _sha256(session_path)

    original_document = parse_session_file(session_path)
    expected_order = json.loads(
        (bundle / "expected_actions.json").read_text(encoding="utf-8")
    )
    assert _normalized_action_order(original_document) == expected_order
    _assert_trace_has_no_synthesized_actions(bundle / "causal_trace.jsonl")

    portable_document = _portable_document(session_path, fixture_name)
    result = replay_session(
        portable_document,
        fixture_base=fixture_base,
        project_folder=project_folder,
    )

    assert result.actions_run == len(original_document.actions)
    assert _sha256(session_path) == session_digest_before
    _assert_manifest(bundle)
    expected_artifact_digest = (
        bundle / "canonical-artifacts.sha256"
    ).read_text(encoding="utf-8").strip()
    assert _canonical_artifact_sha256(result.project_folder) == expected_artifact_digest
    if scenario == "archive_success":
        _assert_archive_output(bundle, result.project_folder)
    return result.project_folder


def _restore_viewport_recording_paths(project_folder: Path) -> None:
    """CODEX: Restore historical paths retained by the copied viewport fixture.

    CODEX: The later recordings copied the viewport project without rebasing
    CODEX: its durable image, audit, or model paths. Reproducing that declared
    CODEX: input state keeps their approved canonical output path-independent.
    """

    prepared_folder = project_folder.resolve().as_posix()
    database_path = project_file_path(project_folder, DATABASE_FILENAME)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            UPDATE project_images
            SET image_path = replace(image_path, ?, ?)
            """,
            (prepared_folder, VIEWPORT_RECORDED_FOLDER),
        )
        connection.execute(
            """
            UPDATE audit_events
            SET details_json = replace(details_json, ?, ?)
            """,
            (prepared_folder, VIEWPORT_RECORDED_FOLDER),
        )
        connection.commit()
    finally:
        connection.close()

    for filename in ("audit_events.jsonl", "model.conf"):
        artifact_path = project_file_path(project_folder, filename)
        artifact_text = artifact_path.read_text(encoding="utf-8")
        artifact_path.write_text(
            artifact_text.replace(prepared_folder, VIEWPORT_RECORDED_FOLDER),
            encoding="utf-8",
        )


def _replay_viewport_fixture_process(
    fixture_base: Path,
    fixture_name: str,
    project_folder: Path,
) -> None:
    """CODEX: Build viewport state in the separate process used when recorded."""

    from tools.e2e_session.session_preferences import session_preferences

    with session_preferences(project_folder):
        _replay_authoritative_recording(
            "viewport_overlay_controls",
            fixture_base,
            fixture_name,
            project_folder,
        )


def _run_viewport_fixture_replay(
    fixture_base: Path,
    fixture_name: str,
    project_folder: Path,
) -> None:
    """CODEX: Launch the viewport fixture replay with fresh process state."""

    child_script = (
        "from pathlib import Path; import sys; "
        "from tests.e2e.test_authoritative_manual_tk_recordings import "
        "_replay_viewport_fixture_process; "
        "_replay_viewport_fixture_process(Path(sys.argv[1]), sys.argv[2], "
        "Path(sys.argv[3]))"
    )
    subprocess.run(
        [
            sys.executable,
            "-c",
            child_script,
            fixture_base,
            fixture_name,
            project_folder,
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )


def _prepare_fixture(scenario: str, tmp_path: Path) -> tuple[Path, str]:
    """CODEX: Build the pre-recording project state required by one scenario."""

    fixture_base = tmp_path / "fixtures"
    fixture_base.mkdir()
    if scenario == "startup_cancel_toolbar_load":
        # CODEX: This scenario begins without a project so toolbar Load owns
        # CODEX: the initial installation of the pristine image fixture.
        source = FIXTURE_ROOT / "teacup_e2e_images"
    else:
        source = FIXTURE_ROOT / "master_2"

    if scenario in VIEWPORT_DERIVED_SCENARIOS:
        # CODEX: Replaying the protected viewport session reproduces the
        # CODEX: established database state used by later recordings.
        viewport_fixture_name = "viewport_source"
        shutil.copytree(source, fixture_base / viewport_fixture_name)
        source = tmp_path / "viewport_baseline"
        _run_viewport_fixture_replay(fixture_base, viewport_fixture_name, source)
        _restore_viewport_recording_paths(source)

    fixture_name = f"{scenario}_source"
    destination = fixture_base / fixture_name
    shutil.copytree(source, destination)

    # CODEX: Each mutation reproduces the exact copied-fixture state declared
    # CODEX: before the manual recording.
    if scenario == "configuration_round_trip":
        shutil.copy2(
            EVIDENCE_ROOT / scenario / "manual_profile.conf",
            destination / "manual_profile.conf",
        )
    elif scenario in {
        "reconcile_added_image_accept",
        "reconcile_added_image_reject",
    }:
        shutil.copy2(
            FIXTURE_ROOT / "teacup_e2e_images" / "a4_01_page_147.jpg",
            destination / "manual_added_reconciliation.jpg",
        )
    elif scenario == "reconcile_missing_image_accept":
        (destination / "a4_05_page_314.jpg").unlink()
    elif scenario == "archive_success":
        shutil.copy2(
            EVIDENCE_ROOT / scenario / "class_definitions.txt",
            destination / "teacup" / "class_definitions.txt",
        )

    return fixture_base, fixture_name


def _verify_authoritative_recording(scenario: str, tmp_path: Path) -> None:
    """CODEX: Prepare, replay, and compare one immutable manual Tk bundle."""

    fixture_base, fixture_name = _prepare_fixture(scenario, tmp_path)
    _replay_authoritative_recording(
        scenario,
        fixture_base,
        fixture_name,
        tmp_path / scenario,
    )


def test_authoritative_manual_tk__interleaved_shortcuts(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: BUG-2026-08-26-RECORDER-INTERLEAVED-SHORTCUTS.

    CODEX: Human Tk evidence preserves interleaved modes and selection edits.
    """

    _verify_authoritative_recording("interleaved_shortcuts", tmp_path)


def test_authoritative_manual_tk__startup_cancel_toolbar_load(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: BUG-2026-08-30-RECORDER-COMMAND-LOAD-ORDER.

    CODEX: Human Tk evidence preserves startup cancellation and toolbar loading.
    """

    _verify_authoritative_recording("startup_cancel_toolbar_load", tmp_path)


def test_authoritative_manual_tk__menu_pointer_resize_causality(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: BUG-2026-08-30-RECORDER-MENU-POINTER-OWNERSHIP.

    CODEX: Human Tk evidence preserves menu ownership across geometry and resize.
    """

    _verify_authoritative_recording("menu_pointer_resize_causality", tmp_path)


def test_authoritative_manual_tk__held_vertex_delete_navigation(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Protect held-key vertex deletion and navigation evidence.

    CODEX: BUG-2026-08-27-RECORDER-DROPS-HELD-VERTEX-KEYS.
    CODEX: BUG-2026-08-30-RECORDER-MISSES-VIEW-NAVIGATION.
    CODEX: BUG-2026-08-30-RECORDER-COLLAPSES-MIXED-AUDIT.
    """

    _verify_authoritative_recording("held_vertex_delete_navigation", tmp_path)


def test_authoritative_manual_tk__held_rectangle_key_repeat(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: BUG-2026-08-30-RECORDER-KEY-REPEAT-OBSERVATION-DRIFT.

    CODEX: Human Tk evidence preserves held rectangle repeat causality.
    """

    _verify_authoritative_recording("held_rectangle_key_repeat", tmp_path)


def test_authoritative_manual_tk__individual_vertex_insert_move_delete(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves vertex insertion, left-button
    CODEX: movement, and immediate middle-press deletion.
    """

    _verify_authoritative_recording(
        "individual_vertex_insert_move_delete",
        tmp_path,
    )


def test_authoritative_manual_tk__arrow_crossing_secondary_edits_preserve_polygon(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves polygon state across crossing-arrow edits."""

    _verify_authoritative_recording(
        "arrow_crossing_secondary_edits_preserve_polygon",
        tmp_path,
    )


def test_authoritative_manual_tk__drawing_shortcuts_from_non_canvas_controls(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves drawing shortcuts from non-canvas
    CODEX: controls.
    """

    _verify_authoritative_recording(
        "drawing_shortcuts_from_non_canvas_controls",
        tmp_path,
    )


def test_authoritative_manual_tk__raw_keyboard_navigation_zoom_review_resample(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves raw navigation, keypad zoom,
    CODEX: resampling, and review flagging.
    """

    _verify_authoritative_recording(
        "raw_keyboard_navigation_zoom_review_resample",
        tmp_path,
    )


def test_authoritative_manual_tk__annotation_delete_with_selected_vertices(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: BUG-2026-08-27-RECORDER-MISRECORDS-ANNOTATION-DELETE-AS-VERTEX-DELETE.

    CODEX: Human Tk evidence distinguishes annotation and vertex deletion.
    """

    _verify_authoritative_recording(
        "annotation_delete_with_selected_vertices",
        tmp_path,
    )


def test_authoritative_manual_tk__configuration_round_trip(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves Configuration profile round trips."""

    _verify_authoritative_recording("configuration_round_trip", tmp_path)


def test_authoritative_manual_tk__class_panel_lifecycle(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves the class-panel lifecycle."""

    _verify_authoritative_recording("class_panel_lifecycle", tmp_path)


def test_authoritative_manual_tk__completed_arrow_lifecycle(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves completed-arrow editing and Undo."""

    _verify_authoritative_recording("completed_arrow_lifecycle", tmp_path)


def test_authoritative_manual_tk__navigation_filter_review(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves navigation, filtering, and review."""

    _verify_authoritative_recording("navigation_filter_review", tmp_path)


def test_authoritative_manual_tk__delete_restore_save_confirmation(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves deletion marking and confirmation."""

    _verify_authoritative_recording(
        "delete_restore_save_confirmation",
        tmp_path,
    )


def test_authoritative_manual_tk__model_configuration_failure(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves model-configuration failure handling."""

    _verify_authoritative_recording("model_configuration_failure", tmp_path)


def test_authoritative_manual_tk__polygon_edit_reclassify_resample(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves polygon editing and resampling."""

    _verify_authoritative_recording(
        "polygon_edit_reclassify_resample",
        tmp_path,
    )


def test_authoritative_manual_tk__overlap_delete_undo_merge_reclassify(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves overlap menus, Undo, and merge."""

    _verify_authoritative_recording(
        "overlap_delete_undo_merge_reclassify",
        tmp_path,
    )


def test_authoritative_manual_tk__viewport_overlay_controls(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves viewport and overlay controls."""

    _verify_authoritative_recording("viewport_overlay_controls", tmp_path)


def test_authoritative_manual_tk__turtle_shell_shared_vertex(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves Turtle shell shared-vertex edits."""

    _verify_authoritative_recording("turtle_shell_shared_vertex", tmp_path)


def test_authoritative_manual_tk__close_incomplete_polygon(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence discards an incomplete polygon on Close."""

    _verify_authoritative_recording("close_incomplete_polygon", tmp_path)


def test_authoritative_manual_tk__close_incomplete_arrow(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence discards an incomplete arrow on Close."""

    _verify_authoritative_recording("close_incomplete_arrow", tmp_path)


def test_authoritative_manual_tk__reconcile_added_image_accept(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves accepted added-image reconciliation."""

    _verify_authoritative_recording("reconcile_added_image_accept", tmp_path)


def test_authoritative_manual_tk__reconcile_added_image_reject(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves rejected added-image reconciliation."""

    _verify_authoritative_recording("reconcile_added_image_reject", tmp_path)


def test_authoritative_manual_tk__reconcile_missing_image_accept(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves accepted missing-image reconciliation."""

    _verify_authoritative_recording("reconcile_missing_image_accept", tmp_path)


def test_authoritative_manual_tk__archive_class_definitions_preflight(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves archive class-definition preflight."""

    _verify_authoritative_recording(
        "archive_class_definitions_preflight",
        tmp_path,
    )


def test_authoritative_manual_tk__archive_success(
    e2e_require_tk: None,
    tmp_path: Path,
) -> None:
    """CODEX: Human Tk evidence preserves successful archive creation."""

    _verify_authoritative_recording("archive_success", tmp_path)
