"""CODEX: Protect category-ID translation at COCO JSON I/O boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

import annotator.sqlite as sql_backend
from annotator.coco import CocoDocument
from annotator.coco.constants import POLYGON_ANNOTATION_FILENAME
from annotator.coco.constants import RECTANGLE_ANNOTATION_FILENAME


def test_zero_based_root_json_imports_after_reserved_category(tmp_path: Path) -> None:
    """BUG-2026-09-07-COCO-CATEGORY-OFFSET: zero-based import starts at one."""

    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    categories = [
        {"id": category_id, "name": name, "supercategory": "object"}
        for category_id, name in enumerate(
            ("scale", "caption", "label", "figure", "other")
        )
    ]
    (tmp_path / "annotations.json").write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": categories,
                "annotations": [
                    {
                        "id": 1,
                        "image_id": 1,
                        "category_id": 0,
                        "segmentation": [[1, 1, 8, 1, 8, 8, 1, 8]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document, connection = sql_backend.load_or_import_document(
        tmp_path,
        [image_path],
    )
    try:
        rows = connection.execute(
            """
            SELECT coco_category_id, annotation_family
            FROM annotation_classes
            ORDER BY coco_category_id
            """
        ).fetchall()
        assert [category["id"] for category in document.categories] == [
            1,
            2,
            3,
            4,
            5,
        ]
        assert document.annotations_for(image_path.name)[0].category_id == 1
        assert [tuple(row) for row in rows] == [
            (0, "keypoints"),
            (1, "region"),
            (2, "region"),
            (3, "region"),
            (4, "region"),
            (5, "region"),
        ]
    finally:
        connection.close()


def test_per_image_json_category_id_is_translated_once(tmp_path: Path) -> None:
    """BUG-2026-09-07-COCO-CATEGORY-OFFSET: an overlay stays stable on reopen."""

    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    common_payload = {
        "images": [{"id": 1, "file_name": image_path.name}],
        "categories": [
            {"id": 1, "name": "scale", "supercategory": "object"},
            {"id": 2, "name": "figure", "supercategory": "object"},
        ],
        "annotations": [],
    }
    (tmp_path / "annotations.json").write_text(
        json.dumps(common_payload),
        encoding="utf-8",
    )
    per_image_path = tmp_path / "teacup" / "pi_json" / "image.jpg.json"
    per_image_path.parent.mkdir(parents=True)
    per_image_path.write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": common_payload["categories"],
                "annotations": [
                    {
                        "id": 1,
                        "image_id": 1,
                        "category_id": 1,
                        "segmentation": [[1, 1, 8, 1, 8, 8, 1, 8]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document, connection = sql_backend.load_or_import_document(
        tmp_path,
        [image_path],
    )
    try:
        assert [category["id"] for category in document.categories] == [2, 3]
        assert document.annotations_for(image_path.name)[0].category_id == 2
    finally:
        connection.close()

    reopened, reopened_connection = sql_backend.load_or_import_document(
        tmp_path,
        [image_path],
    )
    try:
        assert [category["id"] for category in reopened.categories] == [2, 3]
        assert reopened.annotations_for(image_path.name)[0].category_id == 2
        reopened.save()
        saved = json.loads(
            (tmp_path / "annotations.json").read_text(encoding="utf-8")
        )
        assert [category["id"] for category in saved["categories"]] == [1, 2]
        assert saved["annotations"][0]["category_id"] == 1
    finally:
        reopened_connection.close()


def test_every_json_export_translates_without_mutating_state(tmp_path: Path) -> None:
    """BUG-2026-09-07-COCO-CATEGORY-OFFSET: every export uses external IDs."""

    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    document = CocoDocument(tmp_path, [image_path])
    document.categories = [
        {"id": 1, "name": "scale", "supercategory": "object"},
        {"id": 2, "name": "figure", "supercategory": "object"},
    ]
    document.add_annotation(
        image_path.name,
        [(1, 1), (8, 1), (8, 8), (1, 8)],
        category_id=1,
        annotation_type="rectangle",
    )
    document.add_annotation(
        image_path.name,
        [(10, 1), (17, 2), (16, 8), (10, 7)],
        category_id=2,
        annotation_type="polygon",
    )

    document.save_image(image_path.name)
    document.save()

    output_paths = {
        "combined": tmp_path / "annotations.json",
        "per_image": tmp_path / "teacup" / "pi_json" / "image.jpg.json",
        "rectangle": tmp_path / "teacup" / RECTANGLE_ANNOTATION_FILENAME,
        "polygon": tmp_path / "teacup" / POLYGON_ANNOTATION_FILENAME,
    }
    payloads = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in output_paths.items()
    }

    assert [category["id"] for category in payloads["combined"]["categories"]] == [
        0,
        1,
    ]
    assert [
        annotation["category_id"]
        for annotation in payloads["combined"]["annotations"]
    ] == [0, 1]
    assert [
        annotation["category_id"]
        for annotation in payloads["per_image"]["annotations"]
    ] == [0, 1]
    assert [
        annotation["category_id"]
        for annotation in payloads["rectangle"]["annotations"]
    ] == [0]
    assert [
        annotation["category_id"]
        for annotation in payloads["polygon"]["annotations"]
    ] == [1]
    assert [category["id"] for category in document.categories] == [1, 2]
    assert [
        annotation.category_id for annotation in document.annotations_for(image_path.name)
    ] == [1, 2]


def test_negative_json_category_definition_is_rejected(tmp_path: Path) -> None:
    """BUG-2026-09-07-COCO-CATEGORY-OFFSET: a negative category fails import."""

    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    (tmp_path / "annotations.json").write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": [{"id": -1, "name": "scale"}],
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=r"COCO JSON categories\[\]\.id must be greater than or equal to zero: -1",
    ):
        CocoDocument.load(tmp_path, [image_path])


def test_negative_json_annotation_category_reference_is_rejected(
    tmp_path: Path,
) -> None:
    """BUG-2026-09-07-COCO-CATEGORY-OFFSET: a negative reference fails import."""

    image_path = tmp_path / "image.jpg"
    Image.new("RGB", (20, 20), "white").save(image_path)
    (tmp_path / "annotations.json").write_text(
        json.dumps(
            {
                "images": [{"id": 1, "file_name": image_path.name}],
                "categories": [{"id": 0, "name": "scale"}],
                "annotations": [
                    {
                        "id": 1,
                        "image_id": 1,
                        "category_id": -1,
                        "segmentation": [[1, 1, 8, 1, 8, 8, 1, 8]],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=(
            r"COCO JSON annotations\[\]\.category_id must be greater than or "
            r"equal to zero: -1"
        ),
    ):
        CocoDocument.load(tmp_path, [image_path])
