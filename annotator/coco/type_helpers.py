"""Classify COCO regions as constrained rectangles or free polygons.

Imported annotations without type metadata may infer their initial type from
geometry. Once loaded, runtime classification follows `annotation_type`
metadata and conservatively defaults every unknown value to polygon.

The resulting two-type contract is shared by GUI editing, hit testing,
snapping, merging, resampling, and split COCO exports. Arrow annotations use
separate state and are not classified here.
"""

from __future__ import annotations

from annotator.coco.models import Annotation


def annotation_type_from_polygons(polygons: list[list[tuple[float, float]]]) -> str:
    """Return the default region type inferred from imported geometry.

    A single four-corner axis-aligned outline is inferred as `rectangle`. Empty
    or multiple outlines, rotated or irregular quadrilaterals, and every other
    shape are inferred as `polygon`.

    This inference supplies metadata only when an imported annotation lacks an
    explicit `annotation_type`. It does not mutate the geometry or override
    existing metadata.
    """

    # Constrained rectangle editing requires exactly one rectangular outline.
    if len(polygons) == 1 and is_axis_aligned_rectangle(polygons[0]):
        return "rectangle"
    return "polygon"


def annotation_export_type(annotation: Annotation) -> str:
    """Return an annotation's canonical runtime region type.

    Despite the function name, this classification is shared by split exports
    and GUI editing behavior. Normalize `raw["annotation_type"]` by converting
    it to text, trimming whitespace, and ignoring case. Only the resulting value
    `rectangle` enables constrained rectangle behavior; missing, empty, unknown,
    or polygon-like values all return `polygon`.

    This function deliberately trusts metadata rather than re-inferring type
    from current geometry. Geometry inference occurs during import when type
    metadata is absent. The conservative polygon fallback prevents malformed
    metadata from accidentally enabling rectangle-only editing constraints.
    """

    # Loaded metadata, not the current outline, owns runtime editing semantics.
    raw_type = str(annotation.raw.get("annotation_type", "")).strip().lower()
    if raw_type == "rectangle":
        return "rectangle"
    return "polygon"


def annotation_matches_export_filter(
    annotation: Annotation,
    annotation_type_filter: str | None,
) -> bool:
    """Return whether a region belongs in the requested split-export type.

    A `None` filter matches both region types for complete payloads. Otherwise,
    compare the annotation's canonical runtime type with the filter exactly.
    Callers therefore use the lowercase canonical values `polygon` and
    `rectangle`; any other filter value matches nothing.

    This predicate does not mutate the annotation or classify arrow annotations.
    """

    # Complete payloads include both canonical region types.
    if annotation_type_filter is None:
        return True
    return annotation_export_type(annotation) == annotation_type_filter


def is_axis_aligned_rectangle(polygon: list[tuple[float, float]]) -> bool:
    """Return whether four points form an axis-aligned rectangle.

    Require exactly four points. Round coordinates to six decimal places,
    require exactly two distinct x-values and two distinct y-values, and verify
    that all four Cartesian corner combinations are present. Vertex order and
    winding do not matter.

    Rotated quadrilaterals, repeated or missing corners, explicitly closed
    five-point outlines, and rectangles collapsed at six-decimal precision
    return `False`. Rounding prevents minor floating-point noise from discarding
    otherwise axis-aligned imported rectangles.
    """

    if len(polygon) != 4:
        return False
    # Compare at six-decimal precision so minor float noise preserves rectangle type.
    xs = sorted({round(point[0], 6) for point in polygon})
    ys = sorted({round(point[1], 6) for point in polygon})
    if len(xs) != 2 or len(ys) != 2:
        return False
    # Order and winding are irrelevant; every Cartesian corner must be present.
    expected = {(xs[0], ys[0]), (xs[1], ys[0]), (xs[1], ys[1]), (xs[0], ys[1])}
    actual = {(round(point[0], 6), round(point[1], 6)) for point in polygon}
    return actual == expected
