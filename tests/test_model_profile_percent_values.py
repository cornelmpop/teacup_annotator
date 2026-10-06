"""Regression tests for literal percent signs in model profiles."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from annotator.model.configuration import read_model_configuration
from annotator.model.configuration import read_rf_detr_checkpoint_metadata


BUG_ID = "BUG-2026-10-05-MODEL-PROFILE-PERCENT-INTERPOLATION"


class ModelProfilePercentValueTests(unittest.TestCase):
    """Same-stem model profiles treat percent signs as literal text."""

    def test_checkpoint_profile_reads_literal_percent_model_name(self) -> None:
        """BUG-2026-10-05-MODEL-PROFILE-PERCENT-INTERPOLATION: model name."""

        torch = pytest.importorskip("torch")
        with tempfile.TemporaryDirectory() as temp_dir:
            weights_path = Path(temp_dir) / "model.pt"
            torch.save({"args": {}}, weights_path)
            weights_path.with_suffix(".conf").write_text(
                "[checkpoint]\n"
                "model_name = Model 100%\n"
                "model_type = segmentation\n"
                "input_resolution = 1008\n"
                "num_classes = 1\n",
                encoding="utf-8",
            )

            self.assertEqual(
                read_rf_detr_checkpoint_metadata(weights_path),
                {
                    "model_type": "segmentation",
                    "input_resolution": 1008,
                    "num_classes": 1,
                    "checkpoint_model_name": "Model 100%",
                    "direct_model_name": "Model 100%",
                },
            )

    def test_percent_class_name_reaches_class_domain_validation(self) -> None:
        """BUG-2026-10-05-MODEL-PROFILE-PERCENT-INTERPOLATION: class error."""

        with tempfile.TemporaryDirectory() as temp_dir:
            weights_path = Path(temp_dir) / "model.pt"
            weights_path.with_suffix(".conf").write_text(
                "[inference]\n"
                "threshold = 0.5\n\n"
                "[classes]\n"
                "0 = figure%bad\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "Class names may contain only alphanumeric characters, _ and -.",
            ):
                read_model_configuration(weights_path)


if __name__ == "__main__":
    unittest.main()
