"""CODEX: Define shared contracts for COCO region-annotation JSON I/O.

The filename constants identify the complete project-root file and optional
polygon-only and rectangle-only exports. ``COCO_JSON_CATEGORY_ID_OFFSET``
defines the fixed translation between external category IDs and the internal
category domain shared by application state and SQLite.

Arrow annotations are not COCO region geometry and therefore have no filename
here. Per-image JSON folder and path ownership lives in
`annotator.project.paths` and `annotator.coco.io`.
"""

from __future__ import annotations

# The complete project-root file contains all COCO region annotations.
ANNOTATION_FILENAME = "annotations.json"

# CODEX: Internal category ID zero is reserved for arrows, so JSON category IDs
# CODEX: cross the application boundary with this fixed offset in either direction.
COCO_JSON_CATEGORY_ID_OFFSET = 1

# Split exports live under `teacup/` and exist only for nonempty region types.
POLYGON_ANNOTATION_FILENAME = "annotations_polygons.json"
RECTANGLE_ANNOTATION_FILENAME = "annotations_rectangles.json"

# Keys are the canonical annotation-type filters consumed by COCO serialization.
SPLIT_ANNOTATION_FILENAMES = {
    "polygon": POLYGON_ANNOTATION_FILENAME,
    "rectangle": RECTANGLE_ANNOTATION_FILENAME,
}
