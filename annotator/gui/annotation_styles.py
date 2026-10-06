"""Own annotation outline and fill styles shared by canvas renderers."""

from __future__ import annotations

from typing import Any
from typing import Protocol

from PIL import ImageColor

from annotator.gui.constants import ANNOTATION_FILL
from annotator.gui.constants import ANNOTATION_OUTLINE
from annotator.gui.model.settings import class_colour_map
from annotator.gui.model.settings import ModelSettingsHost


class AnnotationStyleHost(ModelSettingsHost, Protocol):
    """Model settings and document categories required for annotation styles."""


def annotation_outline(host: AnnotationStyleHost, annotation: Any) -> str:
    """Return the configured outline colour for an annotation class."""

    # CMP: TODO - Explain this - I assume the return here is simply the default
    # style? It should be more clearly documented.
    if host.project.coco is None:
        return ANNOTATION_OUTLINE
    class_name = host.project.coco.category_name_for_id(annotation.category_id)
    return class_colour_map(host).get(class_name, ANNOTATION_OUTLINE)


def annotation_fill(
    host: AnnotationStyleHost,
    annotation: Any,
    colour_map: dict[str, str] | None = None,
) -> tuple[int, int, int, int]:
    """Return the translucent fill colour for one annotation class."""

    # CMP: TODO - See comment for similar lines in the previous function.
    if host.project.coco is None:
        return ANNOTATION_FILL
    if colour_map is None:
        colour_map = class_colour_map(host)
    class_name = host.project.coco.category_name_for_id(annotation.category_id)
    colour = colour_map.get(class_name)

    # CMP: TODO - Explain what would trigger this scenario
    if colour is None:
        return ANNOTATION_FILL

    # CMP: TODO - Explain why we are doing this.
    try:
        red, green, blue = ImageColor.getrgb(colour)[:3]
    except ValueError:
        return ANNOTATION_FILL
    return red, green, blue, ANNOTATION_FILL[3]
