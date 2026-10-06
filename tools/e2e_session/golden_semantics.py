"""CODEX: Compare canonical GUI outputs at their source-image precision boundary.

The canonical projection owns structure, identifiers, and non-geometric values.
This module tolerates only coordinate rounding introduced while a Tk event moves
between source-image floats and integer canvas pixels. Callers own JSON parsing,
file-set checks, and presentation of a readable source diff.
"""

from __future__ import annotations

import re
from typing import Any


COORDINATE_KEYS = frozenset(
    {
        "arrow",
        "bbox",
        "bbox_coords",
        "end_x",
        "end_y",
        "points",
        "polygon_coords",
        "polygons",
        "segmentation",
        "start_x",
        "start_y",
    }
)
AREA_LABEL_PATTERN = re.compile(r"^(.*) \([0-9,]+ px\)$")
ARROW_NUMBER_PATTERN = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
SOURCE_PIXEL_TOLERANCE = 1.0


def semantic_json_mismatch(expected: Any, actual: Any) -> str | None:
    """CODEX: Return the first material mismatch, or ``None`` when equivalent.

    Dictionary structure and ordinary values remain exact. Coordinate fields
    allow one source-image pixel, derived ``area`` values are not independently
    asserted, and annotation/link collections are ordered by their stable IDs.
    Human-facing area labels and arrow log coordinates follow the same rule.
    """

    return _mismatch(expected, actual, coordinate_context=False, path="root")


def _mismatch(
    expected: Any,
    actual: Any,
    *,
    coordinate_context: bool,
    path: str,
) -> str | None:
    """CODEX: Recursively compare one canonical JSON value and report its path."""

    if isinstance(expected, dict) and isinstance(actual, dict):
        if set(expected) != set(actual):
            return f"{path}: expected keys {sorted(expected)}, got {sorted(actual)}"
        for key in expected:
            if key == "area":
                continue
            expected_value = _ordered_collection(key, expected[key])
            actual_value = _ordered_collection(key, actual[key])
            mismatch = _mismatch(
                expected_value,
                actual_value,
                coordinate_context=coordinate_context or key in COORDINATE_KEYS,
                path=f"{path}.{key}",
            )
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} items, got {len(actual)}"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            mismatch = _mismatch(
                expected_item,
                actual_item,
                coordinate_context=coordinate_context,
                path=f"{path}[{index}]",
            )
            if mismatch is not None:
                return mismatch
        return None
    if coordinate_context and _numbers(expected, actual):
        if abs(expected - actual) <= SOURCE_PIXEL_TOLERANCE:
            return None
        return f"{path}: expected {expected!r}, got {actual!r}"
    if isinstance(expected, str) and isinstance(actual, str):
        if _area_labels_match(expected, actual) or _arrow_logs_match(expected, actual):
            return None
    if expected == actual:
        return None
    return f"{path}: expected {expected!r}, got {actual!r}"


def _ordered_collection(key: str, value: Any) -> Any:
    """CODEX: Stabilize only collections whose SQL identity defines order."""

    if key == "annotations":
        return sorted(value, key=_annotation_identity)
    if key == "annotation_links":
        return sorted(value, key=_annotation_link_identity)
    return value


def _annotation_identity(item: dict[str, Any]) -> Any:
    """CODEX: Return the first stable annotation identity in a projection row."""

    return item.get("annotation_id", item.get("annotation_uuid", item.get("uuid", "")))


def _annotation_link_identity(item: dict[str, Any]) -> Any:
    """CODEX: Return the annotation identity represented by one audit link."""

    record = item.get("after") or item.get("before") or item
    return record.get("annotation_id", item.get("uuid", ""))


def _numbers(left: Any, right: Any) -> bool:
    """CODEX: Return whether both values are JSON numbers rather than booleans."""

    left_number = isinstance(left, (int, float)) and not isinstance(left, bool)
    right_number = isinstance(right, (int, float)) and not isinstance(right, bool)
    return left_number and right_number


def _area_labels_match(expected: str, actual: str) -> bool:
    """CODEX: Compare menu labels while ignoring their derived pixel areas."""

    expected_match = AREA_LABEL_PATTERN.match(expected)
    actual_match = AREA_LABEL_PATTERN.match(actual)
    if expected_match is None or actual_match is None:
        return False
    return expected_match.group(1) == actual_match.group(1)


def _arrow_logs_match(expected: str, actual: str) -> bool:
    """CODEX: Compare arrow log text with source-pixel coordinate tolerance."""

    if not expected.startswith("Arrow") or not actual.startswith("Arrow"):
        return False
    if ARROW_NUMBER_PATTERN.sub("<point>", expected) != ARROW_NUMBER_PATTERN.sub(
        "<point>", actual
    ):
        return False
    # CODEX: Regex text is parsed at the canonical JSON/log boundary.
    expected_numbers = [float(value) for value in ARROW_NUMBER_PATTERN.findall(expected)]
    # CODEX: Regex text is parsed at the canonical JSON/log boundary.
    actual_numbers = [float(value) for value in ARROW_NUMBER_PATTERN.findall(actual)]
    if len(expected_numbers) != len(actual_numbers):
        return False
    return all(
        abs(left - right) <= SOURCE_PIXEL_TOLERANCE
        for left, right in zip(expected_numbers, actual_numbers)
    )
