"""Regression tests for source-aware model annotation replacement."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from annotator.coco import Annotation
from annotator.coco import CocoDocument
from annotator.coco import ModelAnnotation


class ReplaceWithModelAnnotationsTests(unittest.TestCase):
    """Model runs replace untouched output while retaining human-owned work."""

    def test_human_owned_regions_survive_model_replacement(self) -> None:
        """CODEX: Regression model_rerun_destructively_replaces_prior_model_output_2026-08-31."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            document.categories = [
                {"id": 7, "name": "flake", "supercategory": "object"},
                {"id": 11, "name": "other", "supercategory": "object"},
            ]
            image_id = document.image_id_for(image_path.name)
            manual = Annotation(
                annotation_id=1,
                image_id=image_id,
                category_id=7,
                polygons=[[(1, 1), (5, 1), (5, 5), (1, 5)]],
                raw={
                    "annotation_uuid": "ann:manual",
                    "entry_type": "manual",
                    "annotation_type": "polygon",
                },
            )
            imported = Annotation(
                annotation_id=2,
                image_id=image_id,
                category_id=11,
                polygons=[[(6, 1), (10, 1), (10, 5), (6, 5)]],
                raw={
                    "annotation_uuid": "ann:imported",
                    "entry_type": "automatic",
                    "annotation_type": "polygon",
                },
            )
            corrected_model = Annotation(
                annotation_id=3,
                image_id=image_id,
                category_id=7,
                polygons=[[(1, 6), (5, 6), (5, 10), (1, 10)]],
                raw={
                    "annotation_uuid": "ann:corrected-model",
                    "entry_type": "manual",
                    "model_run_class_id": 40,
                    "annotation_type": "polygon",
                },
            )
            old_model = Annotation(
                annotation_id=4,
                image_id=image_id,
                category_id=7,
                polygons=[[(12, 6), (16, 6), (16, 10), (12, 10)]],
                raw={
                    "annotation_uuid": "ann:old-model",
                    "entry_type": "automatic",
                    "model_run_class_id": 41,
                    "annotation_type": "polygon",
                },
            )
            document.annotations_by_image[image_path.name] = [
                manual,
                imported,
                corrected_model,
                old_model,
            ]

            project_category_ids, installed = (
                document.replace_with_model_annotations(
                    [
                        ModelAnnotation(
                            image_name=image_path.name,
                            category_id=99,
                            polygons=[[(2, 12), (8, 12), (8, 18), (2, 18)]],
                            score=0.8,
                        )
                    ],
                    {99: "flake", 3: "new class"},
                )
            )

            annotations = document.annotations_for(image_path.name)
            self.assertEqual(project_category_ids, {99: 7, 3: 12})
            self.assertEqual(
                [
                    annotation.raw["annotation_uuid"]
                    for annotation in annotations[:3]
                ],
                ["ann:manual", "ann:imported", "ann:corrected-model"],
            )
            self.assertNotIn(
                "ann:old-model",
                [annotation.raw["annotation_uuid"] for annotation in annotations],
            )
            self.assertEqual(installed, [annotations[3]])
            self.assertEqual(installed[0].category_id, 7)
            self.assertEqual(installed[0].raw["model_class_index"], 99)
            self.assertEqual(installed[0].raw["entry_type"], "automatic")


if __name__ == "__main__":
    unittest.main()
