"""CODEX: Record Teacup-native model-run provenance and class mappings.

This module owns completed model-run rows, checkpoint metadata captured for
reproducibility, and the raw model-class to project-class mapping used when
model outputs are installed as Teacup annotations.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from annotator.sqlite.connect import _ensure_session
from annotator.sqlite.json import _json_dumps
from annotator.sqlite.json.classes import _upsert_class_rows
from annotator.sqlite.schema import ensure_schema
from annotator.sqlite.time import _unix_time

# CMP: This is just to match what I put in the schema.
MODEL_OUTPUT_TYPE_BY_RF_DETR_TYPE = {
    "detection": "object_detection",
    "segmentation": "instance_segmentation",
}

# CMP: This function can stay for future expandability, but at the moment
# it's a bit silly.
def model_output_type_for_checkpoint(model_type: str) -> str:
    """CODEX: Return the schema value for a checkpoint output family."""

    return MODEL_OUTPUT_TYPE_BY_RF_DETR_TYPE.get(model_type, model_type)


def confidence_threshold_source_key(source_path: Path, weights_path: Path) -> str:
    """CODEX: Return the schema key describing where the threshold came from."""

    source = source_path.resolve()
    model_settings = weights_path.with_suffix(".conf").resolve()
    if source == model_settings:
        return "model_settings_file"
    return "folder_settings_file"


def record_model_run(
    connection: sqlite3.Connection,
    *,
    weights_path: Path,
    model_md5sum: str,
    model_type: str,
    checkpoint_model_name: str,
    checkpoint_resolution: int,
    checkpoint_class_count: int,
    confidence_threshold: float,
    confidence_threshold_source: str,
    preprocessing: dict[str, Any],
    class_names: dict[int, str],
    project_category_ids: dict[int, int],
    class_colours: tuple[str, ...] = (),
    commit: bool = True,
) -> dict[int, int]:
    """CODEX: Insert one completed model run and return class-map row ids.

    ``class_names`` and ``project_category_ids`` share raw checkpoint class
    indices as keys. The latter maps each raw index onto the stable project
    category selected by exact class-name matching, so a checkpoint index
    cannot rename an unrelated project class that happens to use the same COCO
    ID. The returned dictionary is keyed by raw model class index and identifies
    the checkpoint-specific row attached to each accepted model annotation.
    """

    ensure_schema(connection)
    now = _unix_time()
    session_id = _ensure_session(connection)

    # CMP: 'supercategory' doesn't have to be defined here, since we're not
    # using custom supercategories, and _desired_class_rows() already defaults
    # missing supercategory fields to 'object' (currently).
    categories = [
        {
            "id": project_category_ids[class_index],
            "name": class_name,
        }
        for class_index, class_name in class_names.items()
    ]
    class_id_by_category_id = _upsert_class_rows(
        connection,
        categories,
        class_colours,
        class_source="model",
        source_reference=str(weights_path),
        reorder_classes=False,
    )
    cursor = connection.execute(
        """
        INSERT INTO model_runs(
            session_id, run_start_time, run_end_time, model_path, model_md5sum,
            model_output_type, checkpoint_model_name, checkpoint_resolution,
            checkpoint_class_count, confidence_threshold,
            confidence_threshold_source, preprocessing_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            now,
            now,
            str(weights_path),
            model_md5sum,
            model_output_type_for_checkpoint(model_type),
            checkpoint_model_name,
            checkpoint_resolution,
            checkpoint_class_count,
            confidence_threshold,
            confidence_threshold_source,
            _json_dumps(preprocessing),
        ),
    )
    model_run_id = int(cursor.lastrowid)

    model_run_class_ids: dict[int, int] = {}
    for model_class_index, model_class_name in class_names.items():
        project_category_id = project_category_ids[int(model_class_index)]
        class_id = class_id_by_category_id[project_category_id]
        row = connection.execute(
            """
            INSERT INTO model_run_classes(
                model_run_class_uuid, model_run_id, model_class_index,
                model_class_name, class_id, include_in_model_import
            )
            VALUES(?, ?, ?, ?, ?, 1)
            RETURNING model_run_class_id
            """,
            (
                f"mrc:{uuid.uuid4()}",
                model_run_id,
                int(model_class_index),
                model_class_name,
                class_id,
            ),
        ).fetchone()
        model_run_class_ids[int(model_class_index)] = int(row["model_run_class_id"])
    if commit:
        connection.commit()
    return model_run_class_ids
