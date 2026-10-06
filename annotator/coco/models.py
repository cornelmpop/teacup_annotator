"""Define in-memory records for COCO regions and model-produced candidates.

`Annotation` is mutable working state owned by `CocoDocument`.
`ModelAnnotation` transfers inference output into the document without
prematurely assigning COCO IDs or durable application identity.

Arrow annotations use `annotator.arrows.Arrow` and are not represented here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Annotation:
    """Mutable working state for one polygon or rectangle region annotation.

    `annotation_id` and `image_id` are numeric COCO references and may be
    reassigned during complete serialization. Durable application identity
    normally lives in `raw["annotation_uuid"]`. `category_id` references the
    document's shared category vocabulary, while `polygons` contains editable
    image-coordinate outlines.

    `score` records optional detector confidence. `raw` preserves imported and
    application-specific metadata such as annotation type, entry provenance,
    and annotation identity; serialization regenerates standard COCO identity
    and geometry fields from the typed attributes.

    The dataclass is intentionally mutable because editing, class changes,
    geometry normalization, and serialization update annotations in place.
    """

    annotation_id: int
    image_id: int
    category_id: int
    polygons: list[list[tuple[float, float]]]
    score: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "Annotation":
        """Return a structurally independent copy of this annotation.

        Deep copying prevents changes to nested polygon lists or `raw` metadata
        in one instance from affecting the other.
        """

        return copy.deepcopy(self)


@dataclass(frozen=True)
class ModelAnnotation:
    """Frozen transfer record for one region candidate produced by inference.

    The model pipeline supplies an image basename, model category ID,
    image-coordinate polygon geometry, optional confidence, and intended
    polygon or rectangle type. It deliberately supplies no COCO annotation ID,
    image ID, durable component UUID, or entry provenance; `CocoDocument`
    assigns those only after accepting the result.

    `frozen=True` prevents top-level fields from being rebound between inference
    and document installation. The freezing is shallow: the nested polygon
    lists remain mutable and should be treated as result-owned data.
    """

    image_name: str
    category_id: int
    polygons: list[list[tuple[float, float]]]
    score: float | None = None
    annotation_type: str = "polygon"
