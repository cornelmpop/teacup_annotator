"""Contract tests for Save-generated annotation crop exports."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from annotator.coco import CocoDocument
from annotator.project.crops import write_annotation_crops


class WriteAnnotationCropsTests(unittest.TestCase):
    """Crop images and class-local COCO files retain the approved contract."""

    def test_writes_class_local_crops_with_remapped_geometry(self) -> None:
        """Padding, edge clipping, numbering, and JSON coordinates are exact."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "sample.jpg"
            Image.new("RGB", (100, 80), "white").save(image_path)
            document = CocoDocument(
                folder,
                [image_path],
                {
                    "categories": [
                        {"id": 1, "name": "object", "supercategory": "region"},
                        {"id": 2, "name": "flake", "supercategory": "region"},
                    ]
                },
            )
            document.add_annotation(
                image_path.name,
                [(30, 10), (50, 10), (50, 30), (30, 30)],
                category_id=1,
                annotation_type="rectangle",
            )
            document.add_annotation(
                image_path.name,
                [(2, 65), (12, 65), (12, 78), (2, 78)],
                category_id=1,
            )
            document.add_annotation(
                image_path.name,
                [(70, 20), (80, 20), (75, 35)],
                category_id=2,
            )
            original_save = Image.Image.save
            jpeg_options: list[tuple[int | None, int | None]] = []

            def record_save(
                image: Image.Image,
                path: object,
                image_format: str | None = None,
                **options: object,
            ) -> None:
                if image_format == "JPEG":
                    jpeg_options.append(
                        (options.get("quality"), options.get("subsampling"))
                    )
                original_save(image, path, image_format, **options)

            with mock.patch.object(Image.Image, "save", new=record_save):
                output_folder = write_annotation_crops(document, 20)

            object_folder = output_folder / "object"
            flake_folder = output_folder / "flake"
            self.assertEqual(
                sorted(path.name for path in object_folder.glob("*.jpg")),
                ["sample_1.jpg", "sample_2.jpg"],
            )
            self.assertEqual(
                sorted(path.name for path in flake_folder.glob("*.jpg")),
                ["sample_1.jpg"],
            )
            self.assertEqual(jpeg_options, [(100, 0), (100, 0), (100, 0)])

            with Image.open(object_folder / "sample_1.jpg") as crop:
                self.assertEqual(crop.size, (60, 50))
            with Image.open(object_folder / "sample_2.jpg") as crop:
                self.assertEqual(crop.size, (32, 35))

            object_payload = json.loads(
                (object_folder / "annotations.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                object_payload["categories"],
                [{"id": 0, "name": "object", "supercategory": "region"}],
            )
            self.assertEqual(
                [image["file_name"] for image in object_payload["images"]],
                ["sample_1.jpg", "sample_2.jpg"],
            )
            first_annotation = object_payload["annotations"][0]
            self.assertEqual(first_annotation["image_id"], 1)
            self.assertEqual(first_annotation["category_id"], 0)
            self.assertEqual(first_annotation["bbox"], [20, 10, 20, 20])
            self.assertEqual(first_annotation["area"], 400.0)
            self.assertEqual(
                first_annotation["segmentation"],
                [[20, 10, 40, 10, 40, 30, 20, 30]],
            )
            second_annotation = object_payload["annotations"][1]
            self.assertEqual(second_annotation["bbox"], [2, 20, 10, 13])
            self.assertEqual(second_annotation["area"], 130.0)

            flake_payload = json.loads(
                (flake_folder / "annotations.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(flake_payload["images"]), 1)
            self.assertEqual(len(flake_payload["annotations"]), 1)
            self.assertEqual(flake_payload["categories"][0]["id"], 1)

    def test_rebuild_removes_stale_class_crops_and_annotation_files(self) -> None:
        """A later Save publishes only crops for annotations still present."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "sample.jpg"
            Image.new("RGB", (40, 40), "white").save(image_path)
            document = CocoDocument(folder, [image_path])
            document.categories = [
                {"id": 1, "name": "object", "supercategory": "object"}
            ]
            document.add_annotation(
                image_path.name,
                [(5, 5), (15, 5), (15, 15), (5, 15)],
            )
            document.add_annotation(
                image_path.name,
                [(20, 20), (30, 20), (30, 30), (20, 30)],
            )
            write_annotation_crops(document, 0)
            document.delete_annotation(image_path.name, 1)

            output_folder = write_annotation_crops(document, 0)

            class_folder = output_folder / "object"
            self.assertTrue((class_folder / "sample_1.jpg").is_file())
            self.assertFalse((class_folder / "sample_2.jpg").exists())
            payload = json.loads(
                (class_folder / "annotations.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(payload["annotations"]), 1)

    def test_collision_stops_before_replacing_previous_export(self) -> None:
        """Same-stem source images cannot silently overwrite one crop path."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            jpg_path = folder / "sample.jpg"
            jpeg_path = folder / "sample.jpeg"
            Image.new("RGB", (20, 20), "white").save(jpg_path)
            Image.new("RGB", (20, 20), "black").save(jpeg_path)
            document = CocoDocument(folder, [jpg_path, jpeg_path])
            document.categories = [
                {"id": 1, "name": "object", "supercategory": "object"}
            ]
            for image_path in (jpg_path, jpeg_path):
                document.add_annotation(
                    image_path.name,
                    [(2, 2), (10, 2), (10, 10), (2, 10)],
                )
            previous_folder = folder / "teacup" / "crops"
            previous_folder.mkdir(parents=True)
            marker = previous_folder / "previous.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(
                ValueError,
                r"sample\.jpg.*sample\.jpeg.*object/sample_1\.jpg",
            ):
                write_annotation_crops(document, 20)

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_empty_document_replaces_stale_export_with_empty_folder(self) -> None:
        """A Save with no regions leaves no old class crops or class JSON."""

        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir)
            image_path = folder / "sample.jpg"
            Image.new("RGB", (20, 20), "white").save(image_path)
            stale_folder = folder / "teacup" / "crops" / "object"
            stale_folder.mkdir(parents=True)
            (stale_folder / "sample_1.jpg").touch()
            document = CocoDocument(folder, [image_path])

            output_folder = write_annotation_crops(document, 20)

            self.assertTrue(output_folder.is_dir())
            self.assertEqual(list(output_folder.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
