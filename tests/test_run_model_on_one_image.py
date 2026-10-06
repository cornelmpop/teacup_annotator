"""Regression tests for single-image RF-DETR inference."""

from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from annotator.model.inference import run_model_on_one_image


class RunModelOnOneImageTests(unittest.TestCase):
    def test_configured_class_at_background_slot_is_an_annotation(self) -> None:
        """CODEX: BUG-2026-09-05-ROBOFLOW-CLASS-LAYOUT.

        CODEX: A literal platform-profile mapping owns its RF-DETR output ID.
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            model = mock.Mock()
            model.predict.return_value = types.SimpleNamespace(
                xyxy=np.asarray([[0, 0, 20, 20]], dtype=float),
                class_id=np.asarray([1]),
                confidence=np.asarray([0.9]),
                mask=None,
                polygons=None,
            )

            annotations = run_model_on_one_image(
                model,
                image_path,
                threshold=0.5,
                model_class_names={1: "lithic_views"},
                num_classes=1,
                model_input_size=20,
            )

        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0].category_id, 1)
        self.assertEqual(annotations[0].score, 0.9)
        self.assertEqual(annotations[0].annotation_type, "rectangle")
        self.assertEqual(
            annotations[0].polygons,
            [[(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]],
        )

    def test_background_class_is_not_an_annotation(self) -> None:
        """RF-DETR's class at num_classes is its no-object output."""

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            model = mock.Mock()
            model.predict.return_value = types.SimpleNamespace(
                xyxy=np.asarray([[0, 0, 20, 20]], dtype=float),
                class_id=np.asarray([9]),
                confidence=np.asarray([0.9]),
                mask=None,
                polygons=None,
            )

            annotations = run_model_on_one_image(
                model,
                image_path,
                threshold=0.5,
                model_class_names={index: str(index) for index in range(9)},
                num_classes=9,
                model_input_size=20,
            )

        self.assertEqual(annotations, [])
