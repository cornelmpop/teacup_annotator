"""Define durable image-space arrow annotations.

Annotator supports region annotations and arrow annotations. Rectangle and
polygon regions live in `CocoDocument`; arrow annotations use the immutable
`Arrow` value object defined here.

The value object is shared by GUI drawing and editing, SQLite persistence, and
audit serialization. It contains no canvas or view logic: endpoints are stored
in image coordinates, and callers convert them at UI boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import uuid

Point = tuple[float, float]

ARROW_SPEC_CLASS_ID = 0
ARROW_SPEC_CLASS_NAME = "__ARROW_SPEC_CLASS__"
ARROW_SPEC_CLASS_ORDER = 0
ARROW_SPEC_COCO_CATEGORY_ID = 0


@dataclass(frozen=True, slots=True)
class Arrow:
    """One immutable arrow annotation with durable identity and base/tip endpoints.

    `arrow_uuid` is the durable key used by SQLite and audit associations. The
    start point is the arrow base and the end point is its tip. The frozen,
    slotted representation makes arrow annotations cheap to copy during
    endpoint edits and prevents accidental in-place mutation outside the
    persistence workflow.
    """

    arrow_uuid: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float

    @property
    def start(self) -> Point:
        """Return the arrow base point in image coordinates."""

        return (self.start_x, self.start_y)

    @property
    def end(self) -> Point:
        """Return the arrow tip point in image coordinates."""

        return (self.end_x, self.end_y)

    @property
    def coords(self) -> tuple[float, float, float, float]:
        """Return base/tip scalars for geometry, persistence, and audit payloads."""

        return (self.start_x, self.start_y, self.end_x, self.end_y)

    def moved_endpoint(self, endpoint_index: int, point: Point) -> Arrow:
        """Return a copy with one endpoint moved while preserving arrow identity.

        `endpoint_index` follows GUI handle ordering: 0 moves the base and 1
        moves the tip. Other values indicate a caller bug and raise
        `ValueError`.
        """

        # Endpoint indexes mirror the two editable handles drawn by the GUI.
        if endpoint_index == 0:
            return Arrow(
                self.arrow_uuid,
                float(point[0]),
                float(point[1]),
                self.end_x,
                self.end_y,
            )
        if endpoint_index == 1:
            return Arrow(
                self.arrow_uuid,
                self.start_x,
                self.start_y,
                float(point[0]),
                float(point[1]),
            )
        raise ValueError(f"Unknown arrow endpoint index: {endpoint_index}")


def new_arrow(start: Point, end: Point) -> Arrow:
    """Create an arrow annotation with a fresh durable arrow UUID.

    The `arr:` prefix distinguishes arrow-annotation identities from region
    component UUIDs in logs and audit details. UUID4 supplies cross-session
    uniqueness.
    """

    # Normalize endpoints to floats at construction so GUI, SQLite, and audit
    # code all observe the same coordinate representation.
    return Arrow(
        f"arr:{uuid.uuid4()}",
        float(start[0]),
        float(start[1]),
        float(end[0]),
        float(end[1]),
    )
