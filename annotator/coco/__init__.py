"""Public COCO API for Annotator."""

from annotator.coco.constants import ANNOTATION_FILENAME
from annotator.coco.constants import POLYGON_ANNOTATION_FILENAME
from annotator.coco.constants import RECTANGLE_ANNOTATION_FILENAME
from annotator.coco.constants import SPLIT_ANNOTATION_FILENAMES
from annotator.coco.document import CocoDocument
from annotator.coco.models import Annotation
from annotator.coco.models import ModelAnnotation

__all__ = [
    "ANNOTATION_FILENAME",
    "POLYGON_ANNOTATION_FILENAME",
    "RECTANGLE_ANNOTATION_FILENAME",
    "SPLIT_ANNOTATION_FILENAMES",
    "Annotation",
    "ModelAnnotation",
    "CocoDocument",
]
