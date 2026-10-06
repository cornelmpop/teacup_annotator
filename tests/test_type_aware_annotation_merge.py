"""Regression tests for type-aware annotation merging."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union

from annotator.coco import CocoDocument


class TypeAwareAnnotationMergeTests(unittest.TestCase):
    """Merges preserve rectangle semantics only for rectangle-only inputs."""

    def test_rectangle_merges_use_the_enclosing_rectangle(self) -> None:
        """Overlapping and disjoint rectangles merge into one bounding box."""

        cases = (
            (
                [(1, 1), (8, 1), (8, 8), (1, 8)],
                [(6, 6), (14, 6), (14, 14), (6, 14)],
                [(1, 1), (14, 1), (14, 14), (1, 14)],
            ),
            (
                [(1, 2), (4, 2), (4, 6), (1, 6)],
                [(10, 8), (15, 8), (15, 12), (10, 12)],
                [(1, 2), (15, 2), (15, 12), (1, 12)],
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            for primary, secondary, expected in cases:
                with self.subTest(expected=expected):
                    document = CocoDocument.load(folder, [image_path])
                    document.add_annotation(
                        image_path.name, primary, annotation_type="rectangle"
                    )
                    document.add_annotation(
                        image_path.name, secondary, annotation_type="rectangle"
                    )

                    document.merge_annotations(image_path.name, 0, 1)

                    merged = document.annotations_for(image_path.name)[0]
                    self.assertEqual(merged.polygons, [expected])
                    self.assertEqual(merged.raw["annotation_type"], "rectangle")

    def test_any_polygon_input_produces_a_polygon_merge(self) -> None:
        """A mixed merge cannot retain constrained rectangle semantics."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            document = CocoDocument.load(folder, [image_path])
            document.add_annotation(
                image_path.name, [(1, 1), (8, 1), (8, 8), (1, 8)], annotation_type="rectangle"
            )
            document.add_annotation(
                image_path.name, [(6, 6), (14, 6), (14, 14), (6, 14)], annotation_type="rectangle"
            )
            document.add_annotation(
                image_path.name, [(12, 2), (18, 5), (12, 8)], annotation_type="polygon"
            )

            document.merge_annotations(image_path.name, 0, 1)
            document.merge_annotations(image_path.name, 0, 1)

            merged = document.annotations_for(image_path.name)[0]
            self.assertEqual(merged.raw["annotation_type"], "polygon")
            self.assertGreater(len(merged.polygons[0]), 4)

    def test_disconnected_polygon_merge_uses_one_gap_free_outline(self) -> None:
        """Separated polygon pieces merge into one editable exterior outline."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            document = CocoDocument.load(folder, [image_path])
            document.add_annotation(image_path.name, [(0, 0), (2, 0), (2, 2), (0, 2)])
            document.add_annotation(
                image_path.name,
                [(10, 0), (12, 0), (12, 2), (10, 2)],
            )

            merged_index = document.merge_annotations(image_path.name, 0, 1)

            annotations = document.annotations_for(image_path.name)
            self.assertEqual(merged_index, 0)
            self.assertEqual(len(annotations), 1)
            self.assertEqual(len(annotations[0].polygons), 1)
            self.assertEqual(Polygon(annotations[0].polygons[0]).area, 24.0)

    def test_known_bug_regression_ring_merge_does_not_fill_center(self) -> None:
        """Known-bug regression: Adler2002_333_0_13 refuses the ring merge."""

        ring_parts = [
            [(0, 0), (30, 0), (30, 5), (0, 5)],
            [(25, 5), (30, 5), (30, 25), (25, 25)],
            [(0, 25), (30, 25), (30, 30), (0, 30)],
            [(0, 5), (5, 5), (5, 25), (0, 25)],
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (40, 40), "white").save(image_path)
            document = CocoDocument.load(folder, [image_path])
            for polygon in ring_parts:
                document.add_annotation(image_path.name, polygon)

            self.assertEqual(document.merge_annotations(image_path.name, 0, 1), 0)
            self.assertEqual(document.merge_annotations(image_path.name, 0, 1), 0)
            self.assertIsNone(document.merge_annotations(image_path.name, 0, 1))
            document.save_image(image_path.name)

            annotations = document.annotations_for(image_path.name)
            merged_shape = unary_union(
                [
                    Polygon(part)
                    for annotation in annotations
                    for part in annotation.polygons
                ]
            )
            self.assertEqual(len(annotations), 2)
            self.assertAlmostEqual(merged_shape.area, 500.0)
            self.assertFalse(
                merged_shape.contains(
                    Polygon([(10, 10), (20, 10), (20, 20), (10, 20)])
                )
            )
