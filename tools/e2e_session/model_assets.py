"""CODEX: Register and resolve large model files used by GUI sessions.

Session files own only a SHA-256 token. An ignored local registry maps that
identity to a machine-specific checkpoint path, keeping weights out of fixtures,
processed projects, goldens, and Git. Registration and replay verify content;
the model loader continues to own checkpoint and adjacent configuration parsing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
import re

from tools.e2e_session.fixture_file_paths import fixture_file_token
from tools.e2e_session.fixture_file_paths import resolve_fixture_file_token
from tools.e2e_session.session_format import SessionDocument


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODEL_ASSET_REGISTRY_PATH = (
    REPOSITORY_ROOT / "tests" / "e2e" / "model_assets.local.json"
)
MODEL_ASSET_PREFIX = "<model-asset>/"
MODEL_WEIGHT_DIALOG_TITLES = frozenset(
    {"Select model weights", "Select RF-DETR weights"}
)
REGISTER_MODEL_ASSET_COMMAND = (
    "python tools/register_e2e_model_asset.py /path/to/checkpoint.pt"
)


def register_model_asset(path: Path, registry_path: Path) -> str:
    """CODEX: Record PATH under its streaming SHA-256 identity and return its token.

    The registry stores only the resolved local path. It does not copy, parse,
    or validate model contents; callers and the model loader own those
    responsibilities.
    """

    resolved = path.expanduser().resolve()
    digest = _sha256_file(resolved)
    registry = _read_registry(registry_path, missing_ok=True)
    # CODEX: JSON owns text paths; the resolved Path remains authoritative in memory.
    registry[digest] = str(resolved)
    registry_path.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return MODEL_ASSET_PREFIX + digest


def model_weights_file_token(
    selected_path: str,
    project_folder: Path,
    registry_path: Path,
) -> str:
    """CODEX: Return a fixture token or register one external model checkpoint.

    Small project-owned weights remain self-contained in the fixture. An
    external checkpoint is hashed in place and represented through the local
    registry without copying it into an E2E artifact.
    """

    try:
        return fixture_file_token(selected_path, project_folder)
    except ValueError:
        # CODEX: Native chooser text crosses into filesystem identity only when
        # CODEX: the fixture namespace has established that the path is external.
        return register_model_asset(Path(selected_path), registry_path)


def validate_model_asset_token(token: str) -> str:
    """CODEX: Return the lowercase SHA-256 in a canonical model-asset token."""

    if not token.startswith(MODEL_ASSET_PREFIX):
        raise ValueError("model weights must use <model-asset>/SHA256")
    digest = token.removeprefix(MODEL_ASSET_PREFIX)
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("model-asset token must contain 64 lowercase hex digits")
    return digest


def resolve_model_asset_token(token: str, registry_path: Path) -> Path:
    """CODEX: Return a registered checkpoint after verifying its recorded digest.

    Registry and file errors, or a content mismatch, propagate to the replay
    preflight boundary so no project or Tk state exists when replay rejects it.
    """

    digest = validate_model_asset_token(token)
    registry = _read_registry(registry_path, missing_ok=False)
    registered_path = registry.get(digest)
    if registered_path is None:
        raise ValueError(f"model asset {token} is not registered locally")
    # CODEX: Registry JSON is the loose path boundary; resolution establishes
    # CODEX: the filesystem identity that replay passes to production.
    path = Path(registered_path).expanduser().resolve()
    actual_digest = _sha256_file(path)
    if actual_digest != digest:
        raise ValueError(
            f"registered model asset content does not match {token}: {path}"
        )
    return path


def resolve_file_token(
    token: str,
    project_folder: Path,
    model_assets: Mapping[str, Path],
) -> Path:
    """CODEX: Resolve one fixture or preflighted model-asset file identity."""

    if token.startswith(MODEL_ASSET_PREFIX):
        validate_model_asset_token(token)
        try:
            return model_assets[token]
        except KeyError as exc:
            raise ValueError(
                f"model asset {token} was not resolved during replay preflight"
            ) from exc
    return resolve_fixture_file_token(token, project_folder)


def required_model_asset_tokens(document: SessionDocument) -> tuple[str, ...]:
    """CODEX: Return unique model-asset tokens referenced by one session."""

    required: dict[str, None] = {}
    for entry in document.entries:
        for field in (*entry.arguments, *entry.observations):
            _key, separator, value = field.partition("=")
            candidate = value if separator else field
            if not candidate.startswith(MODEL_ASSET_PREFIX):
                continue
            try:
                validate_model_asset_token(candidate)
            except ValueError as exc:
                raise AssertionError(f"{entry.location}: {exc}") from exc
            required[candidate] = None
    return tuple(required)


def resolve_required_model_assets(
    document: SessionDocument,
    registry_path: Path,
) -> dict[str, Path]:
    """CODEX: Resolve all required checkpoints before replay creates any state."""

    resolved: dict[str, Path] = {}
    for token in required_model_asset_tokens(document):
        try:
            resolved[token] = resolve_model_asset_token(token, registry_path)
        except (OSError, ValueError) as exc:
            raise AssertionError(
                f"{document.source_name}: required model asset {token} is unavailable: "
                f"{exc}. Register its local copy with: "
                f"{REGISTER_MODEL_ASSET_COMMAND}"
            ) from exc
    return resolved


def _read_registry(registry_path: Path, *, missing_ok: bool) -> dict[str, str]:
    """CODEX: Parse the ignored local JSON registry at its interchange boundary."""

    if missing_ok and not registry_path.exists():
        return {}
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    valid_mapping = isinstance(payload, dict) and all(
        isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
        and isinstance(path, str)
        and bool(path)
        for digest, path in payload.items()
    )
    if not valid_mapping:
        raise ValueError("model asset registry must map SHA-256 digests to paths")
    return payload


def _sha256_file(path: Path) -> str:
    """CODEX: Stream one checkpoint into the content identity stored by sessions."""

    with path.open("rb") as model_file:
        return hashlib.file_digest(model_file, "sha256").hexdigest()
