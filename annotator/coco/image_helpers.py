"""Read optional source-image dimensions for COCO serialization.

COCO image records may include width and height, but those fields are not
required to preserve region annotations. This module uses Pillow to inspect
source-image headers without owning image discovery, display loading, or other
metadata.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def image_size(path: Path) -> tuple[int | None, int | None]:
    """Return the Pillow-reported `(width, height)` for an image path.

    The image is closed before returning. If Pillow cannot open or identify the
    file and raises `OSError`, return `(None, None)`. COCO serializers interpret
    that result as “do not refresh the dimension fields”: existing values
    remain, while new records omit width and height. Other exceptions propagate.
    """

    # Dimensions enrich COCO image records but are not required for region
    # recovery, so an unreadable source image does not block JSON serialization.
    try:
        with Image.open(path) as image:
            return image.size
    except OSError:
        return None, None
