"""Tests for RF-DETR checkpoint metadata and detection geometry."""

from __future__ import annotations

import argparse
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
from PIL import Image

from annotator.coco import CocoDocument
from annotator.model.configuration import read_rf_detr_checkpoint_metadata
from annotator.model.inference import run_model_on_images
from annotator.model.inference import run_model_on_one_image
from annotator.model.workflow import configure_model_run
from annotator.model.workflow import execute_model_run


class RFDetrCheckpointMetadataTests(unittest.TestCase):
    """RF-DETR checkpoints select the matching model and annotation type."""

    def test_checkpoint_metadata_identifies_detection_and_segmentation(self) -> None:
        """The segmentation_head flag is read without loading executable objects."""

        torch = pytest.importorskip("torch")
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for segmentation_head, expected in (
                (False, "detection"),
                (True, "segmentation"),
            ):
                with self.subTest(expected=expected):
                    checkpoint_path = folder / f"{expected}.pt"
                    torch.save(
                        {
                            "args": argparse.Namespace(
                                segmentation_head=segmentation_head,
                                resolution=1024,
                                num_classes=2,
                                class_names=["flake", "core"],
                            )
                        },
                        checkpoint_path,
                    )
                    self.assertEqual(
                        read_rf_detr_checkpoint_metadata(checkpoint_path),
                        {
                            "model_type": expected,
                            "input_resolution": 1024,
                            "num_classes": 2,
                            "checkpoint_model_name": expected,
                        },
                    )

    def test_checkpoint_without_model_type_is_rejected(self) -> None:
        """Unknown checkpoints are not guessed into an incompatible model."""

        torch = pytest.importorskip("torch")
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_path = Path(temp_dir) / "unknown.pt"
            torch.save(
                {"args": argparse.Namespace(resolution=1024)},
                checkpoint_path,
            )

            with self.assertRaisesRegex(ValueError, "does not identify"):
                read_rf_detr_checkpoint_metadata(checkpoint_path)

    def test_checkpoint_without_resolution_is_rejected(self) -> None:
        """Inference does not fall back to an unrelated configured input size."""

        torch = pytest.importorskip("torch")
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_path = Path(temp_dir) / "unknown-resolution.pt"
            torch.save(
                {"args": argparse.Namespace(segmentation_head=False)},
                checkpoint_path,
            )

            with self.assertRaisesRegex(ValueError, "input resolution"):
                read_rf_detr_checkpoint_metadata(checkpoint_path)

    def test_platform_checkpoint_uses_profile_with_checkpoint_name_precedence(
        self,
    ) -> None:
        """CODEX: BUG-2026-09-05-ROBOFLOW-CHECKPOINT-METADATA.

        CODEX: A same-stem profile supplies architecture metadata omitted by a
        CODEX: platform export, while an embedded model name wins when present.
        """

        torch = pytest.importorskip("torch")
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            for checkpoint_name, expected_name in (
                (None, "ProfileVariant"),
                ("CheckpointVariant", "CheckpointVariant"),
            ):
                with self.subTest(checkpoint_name=checkpoint_name):
                    checkpoint_path = folder / f"{expected_name}.pt"
                    checkpoint = {"args": {}}
                    if checkpoint_name is not None:
                        checkpoint["model_name"] = checkpoint_name
                    torch.save(checkpoint, checkpoint_path)
                    checkpoint_path.with_suffix(".conf").write_text(
                        "[checkpoint]\n"
                        "model_name = ProfileVariant\n"
                        "model_type = segmentation\n"
                        "input_resolution = 1008\n"
                        "num_classes = 1\n\n"
                        "[inference]\n"
                        "threshold = 0.5\n\n"
                        "[classes]\n"
                        "0 = outline\n",
                        encoding="utf-8",
                    )

                    configuration = configure_model_run(
                        checkpoint_path,
                        "",
                        folder / "teacup" / "model.conf",
                    )
                    with mock.patch(
                        "annotator.model.workflow.run_model_on_images",
                        return_value=[],
                    ) as run_model:
                        execute_model_run([], configuration)

                    self.assertEqual(configuration.model_type, "segmentation")
                    self.assertEqual(configuration.checkpoint_model_name, expected_name)
                    self.assertEqual(configuration.input_resolution, 1008)
                    self.assertEqual(configuration.num_classes, 1)
                    self.assertEqual(configuration.threshold, 0.5)
                    self.assertEqual(configuration.class_names, {0: "outline"})
                    run_model.assert_called_once_with(
                        [],
                        checkpoint_path,
                        "segmentation",
                        threshold=0.5,
                        model_class_names={0: "outline"},
                        num_classes=1,
                        model_input_size=1008,
                        progress=None,
                        direct_model_name=expected_name,
                    )

    def test_checkpoint_loader_infers_model_variant(self) -> None:
        """The runner lets RF-DETR infer the concrete checkpoint class."""

        loader = mock.Mock()
        model = mock.Mock()
        loader.from_checkpoint.return_value = model
        fake_module = types.SimpleNamespace(RFDETR=loader)
        with (
            mock.patch.dict(sys.modules, {"rfdetr": fake_module}),
            mock.patch(
                "annotator.model.inference.run_model_on_one_image",
                return_value=[],
            ) as run_one,
        ):
            run_model_on_images(
                [Path("a.jpg")],
                Path("weights.pt"),
                "detection",
                threshold=0.5,
                model_class_names={1: "lithics", 2: "map"},
                num_classes=2,
                model_input_size=560,
            )

        loader.from_checkpoint.assert_called_once_with(
            "weights.pt",
            device="cpu",
        )
        run_one.assert_called_once_with(
            model,
            Path("a.jpg"),
            0.5,
            {1: "lithics", 2: "map"},
            2,
            560,
        )

    def test_profile_model_name_selects_model_class(self) -> None:
        """CODEX: BUG-2026-09-05-ROBOFLOW-CHECKPOINT-METADATA.

        CODEX: Explicit profile metadata selects the named RF-DETR class without
        CODEX: asking the generic checkpoint loader to infer the missing variant.
        """

        loader = mock.Mock()
        model_class = mock.Mock()
        model_class.return_value = mock.Mock()
        fake_module = types.SimpleNamespace(
            RFDETR=loader,
            ConfiguredVariant=model_class,
        )
        with mock.patch.dict(sys.modules, {"rfdetr": fake_module}):
            results = run_model_on_images(
                [],
                Path("weights.pt"),
                "segmentation",
                threshold=0.5,
                model_class_names={0: "outline"},
                num_classes=1,
                model_input_size=1008,
                direct_model_name="ConfiguredVariant",
            )

        self.assertEqual(results, [])
        model_class.assert_called_once_with(
            pretrain_weights="weights.pt",
            device="cpu",
            num_classes=1,
            resolution=1008,
        )
        loader.from_checkpoint.assert_not_called()

    def test_missing_rfdetr_error_names_teacup_model_support(self) -> None:
        """Optional dependency guidance is understandable to Teacup users."""

        with mock.patch.dict(sys.modules, {"rfdetr": None}):
            with self.assertRaisesRegex(ImportError, "Teacup Annotator") as raised:
                run_model_on_images(
                    [Path("a.jpg")],
                    Path("weights.pt"),
                    "detection",
                    threshold=0.5,
                    model_class_names={1: "lithics"},
                    num_classes=2,
                    model_input_size=560,
                )

        self.assertNotIn("Lithics2D", str(raised.exception))

    def test_detection_box_becomes_a_rectangle_annotation(self) -> None:
        """Box-only predictions retain rectangle editing semantics."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "a.jpg"
            Image.new("RGB", (20, 10), "red").save(image_path)
            detections = types.SimpleNamespace(
                xyxy=np.asarray([[0, 140, 560, 420]], dtype=float),
                class_id=np.asarray([4]),
                confidence=np.asarray([0.9]),
                mask=None,
                polygons=None,
            )
            model = mock.Mock()
            model.predict.return_value = detections

            results = run_model_on_one_image(
                model,
                image_path,
                threshold=0.5,
                model_class_names={4: "lithics"},
                num_classes=5,
                model_input_size=560,
            )
            document = CocoDocument.load(folder, [image_path])
            document.categories = [
                {"id": 1, "name": "object", "supercategory": "object"}
            ]
            project_category_ids, installed = (
                document.replace_with_model_annotations(results, {4: "lithics"})
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].category_id, 4)
            self.assertEqual(results[0].annotation_type, "rectangle")
            self.assertEqual(
                results[0].polygons,
                [[(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)]],
            )
            model_input = model.predict.call_args.args[0]
            self.assertEqual(model_input.size, (560, 560))
            self.assertEqual(model_input.getpixel((0, 0)), (255, 255, 255))
            self.assertGreater(model_input.getpixel((280, 280))[0], 200)
            model.predict.assert_called_once_with(
                mock.ANY,
                threshold=0.5,
                shape=(560, 560),
            )
            self.assertEqual(
                document.annotations_for("a.jpg")[0].raw["annotation_type"],
                "rectangle",
            )
            self.assertEqual(project_category_ids, {4: 2})
            self.assertEqual(installed[0].category_id, 2)
            self.assertEqual(
                document.categories,
                [
                    {"id": 1, "name": "object", "supercategory": "object"},
                    {"id": 2, "name": "lithics", "supercategory": "object"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
