"""Regression tests for atomic combined and split COCO backup writes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from annotator.coco import CocoDocument
from annotator.coco.constants import POLYGON_ANNOTATION_FILENAME


OLD_BACKUP = '{"generation": "old"}\n'


def _document_with_polygon(folder: Path) -> CocoDocument:
    image_path = folder / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(folder, [image_path])
    document.add_annotation(
        image_path.name,
        [(1, 1), (8, 1), (8, 8), (1, 8)],
        annotation_type="polygon",
    )
    return document


def _write_partial_json_then_fail(payload, output_file, *, indent):
    del payload, indent
    output_file.write('{"generation": "partial"')
    raise OSError("injected aggregate backup failure")


class AtomicCocoBackupWriteTests(unittest.TestCase):
    """Combined and split output preserves the previous complete file."""

    def test_combined_backup_failure_preserves_existing_file(self) -> None:
        """BUG-2026-08-19-JSON-BACKUP-REFRESH-NOT-TRANSACTIONAL: combined."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            document = _document_with_polygon(folder)
            output_path = folder / "annotations.json"
            output_path.write_text(OLD_BACKUP, encoding="utf-8")

            with (
                mock.patch(
                    "annotator.coco.io.json.dump",
                    side_effect=_write_partial_json_then_fail,
                ),
                self.assertRaisesRegex(
                    OSError,
                    "^injected aggregate backup failure$",
                ),
            ):
                document.save()

            self.assertEqual(output_path.read_text(encoding="utf-8"), OLD_BACKUP)

    def test_split_backup_failure_preserves_existing_file(self) -> None:
        """BUG-2026-08-19-JSON-BACKUP-REFRESH-NOT-TRANSACTIONAL: split."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            document = _document_with_polygon(folder)
            project_folder = folder / "teacup"
            project_folder.mkdir()
            output_path = project_folder / POLYGON_ANNOTATION_FILENAME
            output_path.write_text(OLD_BACKUP, encoding="utf-8")

            with (
                mock.patch(
                    "annotator.coco.io.json.dump",
                    side_effect=_write_partial_json_then_fail,
                ),
                self.assertRaisesRegex(
                    OSError,
                    "^injected aggregate backup failure$",
                ),
            ):
                document.save_split_annotations()

            self.assertEqual(output_path.read_text(encoding="utf-8"), OLD_BACKUP)


if __name__ == "__main__":
    unittest.main()
