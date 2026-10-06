"""Estimate vertex-ID label bounds and detect collisions between them.

These helpers operate on canvas-space dimensions and boxes without querying Tk
widgets or font metrics. This gives the main and zoom canvases one deterministic
layout calculation. GUI modules own label placement, filtering, and drawing.
"""

from __future__ import annotations

from annotator.geom.rectangle import boxes_overlap

def vertex_label_size(text: str) -> tuple[float, float]:
    """Return the estimated canvas-space width and height of a vertex-ID label.

    Use a fixed height of 14 canvas units. Estimate width as seven units per
    character plus six units of horizontal padding, with a minimum width of 14
    so short labels remain approximately square.

    This is not an actual font measurement. Changes to the GUI's vertex-ID font
    may require corresponding changes to this estimate.
    """

    # Keep short IDs roughly square, widening the box as the character count grows.
    return max(14.0, len(text) * 7.0 + 6.0), 14.0


def label_boxes_overlap(boxes: list[tuple[float, float, float, float]]) -> bool:
    """Return whether any two canvas-space label boxes overlap.

    Each box uses normalized `(left, top, right, bottom)` coordinates and is
    expected to have positive width and height. Containment counts as overlap,
    but boxes that meet only along an edge or at a corner do not. Empty and
    single-box lists return `False`.

    Stop at the first overlapping pair because callers need only know whether
    the complete label layout can be displayed without collisions.
    """

    # Compare each unordered pair once; only the existence of a collision matters.
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            if boxes_overlap(first, second):
                return True
    return False
