"""Input transition records, actions, facts, and shared drag geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from enum import auto

from annotator.gui.state import InteractionState
from annotator.gui.state import Point
from annotator.gui.state import Rectangle


class InputAction(Enum):
    """Controller operation selected by a Tk-free input transition."""

    NONE = auto()
    ZOOM_IN = auto()
    ZOOM_OUT = auto()
    PREVIOUS_IMAGE = auto()
    NEXT_IMAGE = auto()
    CANCEL_SELECTION_OR_MODE = auto()
    DELETE_SELECTED_VERTICES = auto()
    ATTEMPT_AUTOCLOSE = auto()
    DELETE_SELECTED_ANNOTATION_OR_ARROW = auto()
    SIMPLIFY_SELECTED_ANNOTATION = auto()
    START_NEW_ANNOTATION = auto()
    START_NEW_RECTANGLE = auto()
    START_DRAW_ARROW = auto()
    TOGGLE_REVIEW_FLAG = auto()
    FINISH_SELECT_START = auto()
    ADD_NEW_POLYGON_POINT = auto()
    HANDLE_ARROW_CLICK = auto()
    FINISH_MERGE = auto()
    DELETE_AT_POINT = auto()
    BEGIN_ARROW_ENDPOINT_DRAG = auto()
    BEGIN_VERTEX_DRAG = auto()
    BEGIN_RECTANGLE_SIDE_DRAG = auto()
    INSERT_VERTEX = auto()
    START_PAN = auto()
    DRAG_ARROW_ENDPOINT = auto()
    DRAG_VERTEX = auto()
    PAN = auto()
    FINISH_ARROW_ENDPOINT_DRAG = auto()
    FINISH_VERTEX_DRAG = auto()
    FINISH_NEW_RECTANGLE = auto()
    SELECT_OBJECTS_IN_RECT = auto()
    SHOW_VERTEX_SELECTION_MENU = auto()
    SHOW_CANVAS_MENU = auto()
    DELETE_VERTEX = auto()
    MOTION_OUTSIDE_IMAGE = auto()
    MOTION_ARROW = auto()
    MOTION_NEW_POLYGON = auto()
    MOTION_IMAGE = auto()
    LEAVE_CANVAS = auto()
    ZOOM_AT_POINTER = auto()
    SCROLL_HORIZONTAL = auto()
    SCROLL_VERTICAL = auto()


@dataclass(frozen=True, slots=True)
class InputBindings:
    """Resolved single-key bindings needed by keyboard transitions."""

    multi_select: str
    autoclose: str
    delete_annotation: str
    simplify_polygon: str
    new_polygon: str
    new_rectangle: str
    draw_arrow: str
    flag_review: str


@dataclass(frozen=True, slots=True)
class PointerFacts:
    """Read-only hit-test and geometry facts for one pointer event."""

    canvas_point: Point
    image_point: Point | None = None
    annotation_index: int | None = None
    arrow_index: int | None = None
    arrow_endpoint_index: int | None = None
    vertex_ref: tuple[int, int] | None = None
    rectangle_side_ref: tuple[int, int] | None = None
    border_ref: tuple[int, int] | None = None
    selected_annotation_present: bool = False
    selected_annotation_is_rectangle: bool = False
    multiple_annotations_selected: bool = False
    inside_vertex_selection: bool = False
    selection_rect: Rectangle | None = None
    selected_vertices: frozenset[tuple[int, int]] = frozenset()


@dataclass(frozen=True, slots=True)
class InputTransition:
    """Replacement interaction state and its requested controller action."""

    interaction: InteractionState
    action: InputAction = InputAction.NONE
    consumed: bool = False
    redraw: bool = False


def completed_drag_rect(
    start: Point | None,
    current: Point,
) -> Rectangle | None:
    """Return normalized bounds from a drag start and current point."""

    if start is None:
        return None
    return (
        min(start[0], current[0]),
        min(start[1], current[1]),
        max(start[0], current[0]),
        max(start[1], current[1]),
    )
