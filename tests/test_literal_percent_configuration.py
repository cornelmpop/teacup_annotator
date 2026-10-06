"""Regression tests for literal percent signs in configuration values."""

from pathlib import Path
import tempfile
import unittest

from annotator.model.configuration import read_model_conf
from annotator.model.configuration import save_model_conf
from annotator.preferences.files import load_preference_values
from annotator.preferences.files import save_preference_values


class LiteralPercentConfigurationTests(unittest.TestCase):
    """Configuration persistence treats user values as literal text."""

    def test_preference_values_round_trip_literal_percent_signs(self) -> None:
        """BUG-2026-10-04-LITERAL-PERCENT-CONFIG: save literal `%` values."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            preferences_path = root / "annotator_prefs.conf"
            values = {
                "last_image_folder": str(root / "100% complete"),
                "project_description": "reviewed 25% complete",
            }

            save_preference_values(preferences_path, values)

            self.assertEqual(load_preference_values(preferences_path), values)

    def test_preference_file_loads_literal_percent_sign(self) -> None:
        """BUG-2026-10-04-LITERAL-PERCENT-CONFIG: read a literal `%` path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            preferences_path = root / "annotator_prefs.conf"
            percent_path = str(root / "100% complete")
            preferences_path.write_text(
                f"[prefs]\nlast_image_folder = {percent_path}\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_preference_values(preferences_path),
                {"last_image_folder": percent_path},
            )

    def test_folder_model_conf_round_trips_literal_percent_path(self) -> None:
        """BUG-2026-10-04-LITERAL-PERCENT-CONFIG: save a `%` model path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            values = {
                "model_weights": str(folder / "models" / "100% complete" / "model.pt"),
                "default_threshold": "0.63",
            }

            save_model_conf(folder, values)

            self.assertEqual(read_model_conf(folder), values)

    def test_folder_model_conf_loads_literal_percent_path(self) -> None:
        """BUG-2026-10-04-LITERAL-PERCENT-CONFIG: read a `%` model path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            project_data_folder = folder / "teacup"
            project_data_folder.mkdir()
            weights_path = str(folder / "models" / "100% complete" / "model.pt")
            (project_data_folder / "model.conf").write_text(
                f"[model]\nmodel_weights = {weights_path}\n",
                encoding="utf-8",
            )

            self.assertEqual(
                read_model_conf(folder),
                {"model_weights": weights_path},
            )


if __name__ == "__main__":
    unittest.main()
