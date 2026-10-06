"""Regression tests for reporting lossy or rejected COCO imports."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon

from annotator.coco import CocoDocument


class CocoImportReportingTests(unittest.TestCase):
    """JSON import identifies material geometry changes and rejected rows."""

    def test_disconnected_polygons_report_single_outline_conversion(self) -> None:
        """BUG-2026-10-05-LOSSY-COCO-IMPORT-NOT-REPORTED: multipart."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            payload = {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": [{"id": 1, "name": "object"}],
                "annotations": [
                    {
                        "id": 7,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [
                            [0, 0, 2, 0, 2, 2, 0, 2],
                            [8, 0, 10, 0, 10, 2, 8, 2],
                        ],
                    }
                ],
            }
            (folder / "annotations.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            document = CocoDocument.load(folder, [image_path])

        annotation = document.annotations_for(image_path.name)[0]
        self.assertEqual(Polygon(annotation.polygons[0]).area, 20.0)
        self.assertEqual(
            document.import_notices,
            [
                "annotations.json row 1: combined 2 source polygons into one "
                "editable outline (disconnected parts use their convex hull)."
            ],
        )

    def test_interior_hole_reports_flattening(self) -> None:
        """BUG-2026-10-05-LOSSY-COCO-IMPORT-NOT-REPORTED: interior hole."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (40, 40), "white").save(image_path)
            payload = {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": [{"id": 1, "name": "object"}],
                "annotations": [
                    {
                        "id": 8,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [
                            [0, 0, 30, 0, 30, 5, 0, 5],
                            [25, 5, 30, 5, 30, 25, 25, 25],
                            [0, 25, 30, 25, 30, 30, 0, 30],
                            [0, 5, 5, 5, 5, 25, 0, 25],
                        ],
                    }
                ],
            }
            (folder / "annotations.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            document = CocoDocument.load(folder, [image_path])

        annotation = document.annotations_for(image_path.name)[0]
        self.assertEqual(Polygon(annotation.polygons[0]).area, 900.0)
        self.assertEqual(
            document.import_notices,
            [
                "annotations.json row 1: combined 4 source polygons into one "
                "editable outline (disconnected parts use their convex hull); "
                "flattened interior holes."
            ],
        )

    def test_rejected_rows_report_exact_reasons(self) -> None:
        """BUG-2026-10-05-LOSSY-COCO-IMPORT-NOT-REPORTED: rejected rows."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            payload = {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": [{"id": 1, "name": "object"}],
                "annotations": [
                    {
                        "id": 2,
                        "image_id": "bad",
                        "category_id": 1,
                        "segmentation": [[1, 1, 5, 1, 5, 5, 1, 5]],
                    },
                    {
                        "id": 3,
                        "image_id": 99,
                        "category_id": 1,
                        "segmentation": [[1, 1, 5, 1, 5, 5, 1, 5]],
                    },
                    {
                        "id": 4,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": {"counts": "RLE", "size": [20, 20]},
                    },
                    {
                        "id": 5,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [[1, 1, 5, 1, 5, 5, 1, 5]],
                    },
                ],
            }
            (folder / "annotations.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            document = CocoDocument.load(folder, [image_path])

        self.assertEqual(len(document.annotations_for(image_path.name)), 1)
        self.assertEqual(
            document.import_notices,
            [
                "annotations.json row 1: rejected because image, annotation, or "
                "category IDs are not integers.",
                "annotations.json row 2: rejected because image_id 99 does not "
                "match a loaded image.",
                "annotations.json row 3: rejected because it has no supported "
                "editable segmentation, polygons_xy, or bbox geometry.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
