/* CODEX:
Teacup Annotator SQL schema

This is the first version of the schema that upgrades arrows to full annotation status,
and enables future COCO-like annotation types without object-specific tables. This
schema also greatly simplifies the previous version, which maintained compatibility
with a separate project.

Version date: August 18, 2026

Copyright (c) 2026 Cornel M. Pop
SPDX-License-Identifier: GPL-2.0-or-later

AI-assisted drafting and implementation support: OpenAI Codex.
Human direction, selection, review, revision, and integration: Cornel M. Pop.

*/

PRAGMA foreign_keys = ON;

/* CODEX/CMP: Keep track of current schema version, so Teacup can gracefully handle
   compatibility issues. Note that application version and schema version are
   not necessarily the same. Schema version records the version of the application
   where the latest changes were introduced, but there may be newer application
   versions that didn't modify the schema. */
CREATE TABLE schema_metadata (
    schema_key TEXT PRIMARY KEY,
    schema_value TEXT NOT NULL,
    schema_updated_time INTEGER NOT NULL -- CODEX/CMP: Store UTC Unix seconds.
);

INSERT INTO schema_metadata (schema_key, schema_value, schema_updated_time)
VALUES ('schema_version', '1.9.4', 1787096985); -- CODEX/CMP: Record the schema release time.

/* CODEX/CMP: Keep track of schema implementations on database initialization. This
   can be used to manage migrations. */
CREATE TABLE schema_implementations (
    schema_implementation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    implementation_type TEXT NOT NULL, -- CODEX/CMP: Records the implementation kind, such as initialization.
    applied_time INTEGER NOT NULL, -- CODEX/CMP: Store UTC Unix seconds.
    from_schema_version TEXT,
    to_schema_version TEXT NOT NULL,
    app_version TEXT NOT NULL,
    summary TEXT
);

INSERT INTO schema_implementations (
    implementation_type,
    applied_time,
    from_schema_version,
    to_schema_version,
    app_version,
    summary
)
VALUES (
    'initialization',
    unixepoch(),
    NULL,
    '1.9.4',
    '0.9.8',
    'Initialized Teacup-native schema'
);


/* CODEX/CMP: Record session information, so that all actions can be traced to
   specific sessions. Note that this is compatible with folders being
   worked on on different machines. */
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,      -- CODEX/CMP: This is a UUID for the application process. It does NOT record an integer system process ID or an autoincrement integer.
    app_version TEXT NOT NULL,        -- CODEX/CMP: Renames legacy sessions.soft_ver to identify the Teacup application version explicitly.
    started_time INTEGER NOT NULL,    -- CODEX/CMP: Renames legacy sessions.run_time because this records session start time.
                                      -- CODEX/CMP: Store UTC Unix seconds; display code converts timestamps to the user's local/session timezone when presenting dates.
    session_timezone TEXT NOT NULL,   -- CODEX/CMP: Record the IANA timezone, such as America/Vancouver, for audit readability without reinterpreting stored UTC timestamps.
    hostname TEXT NOT NULL,
    host_type TEXT NOT NULL,
    os TEXT NOT NULL
);

/* CODEX/CMP: Record events in a simple freeform text format. Nothing more
   complex seems required. */
CREATE TABLE logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    log_timestamp INTEGER NOT NULL, -- CODEX/CMP: UTC Unix seconds.
    log_entry TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

/* CODEX/CMP: Projects correspond to specific folders, at the moment (i.e., no
   sub-folder structure is supported). This table stores information
   on the images within the current folder/project. */
CREATE TABLE project_images (
    image_id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_name TEXT NOT NULL UNIQUE,
    image_path TEXT NOT NULL,
    image_md5sum TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    coco_image_id INTEGER UNIQUE NOT NULL, -- CODEX: COCO/interchange image id preserved from imported COCO when available or assigned by Teacup for export; internal relationships use image_id.
    image_sequence_index INTEGER NOT NULL, -- CODEX/CMP: New field for the image's stable position in Teacup's review/navigation queue; for future use - I may want to sort by e.g., filename prefix. Note that, since it is not unique, it should be used as a sort hint/order value with a deterministic tie breaker.
    pending_review INTEGER NOT NULL DEFAULT 0 CHECK(pending_review IN (0, 1)),
    marked_for_deletion INTEGER NOT NULL DEFAULT 0 CHECK(marked_for_deletion IN (0, 1)), -- CODEX: Records the user's requested deletion before Teacup performs any filesystem operation.
    moved_to_trash INTEGER NOT NULL DEFAULT 0 CHECK(moved_to_trash IN (0, 1)),           -- CODEX: Records that the requested deletion has already been applied so save/archive code does not repeat the file move.
    metadata_json TEXT NOT NULL DEFAULT '{}' -- CODEX/CMP: Stores optional image-level metadata imported from source files or COCO records
);

/* CODEX/CMP: Stores information on individual model runs, so model-derived annotations can be traced to specific model settings. */
CREATE TABLE model_runs (
    model_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    run_start_time INTEGER NOT NULL, -- CODEX/CMP: Store UTC Unix seconds
    run_end_time INTEGER NOT NULL, -- CODEX/CMP: Store UTC Unix seconds
    model_path TEXT NOT NULL,
    model_md5sum TEXT NOT NULL,
    model_output_type TEXT NOT NULL CHECK(model_output_type IN ('object_detection', 'instance_segmentation', 'keypoint_detection')), -- CODEX/CMP: Records the model-output family for provenance and later importer/exporter dispatch.
    checkpoint_model_name TEXT NOT NULL, -- CODEX/CMP: Records which model family was used, mostly for convenience. This is resolved from the model checkpoint, and examples include RFDETRSegMedium.
    checkpoint_resolution INTEGER NOT NULL, -- CODEX/CMP: Records the model's expected input resolution, as resolved from the model's checkpoint.
    checkpoint_class_count INTEGER NOT NULL, -- CODEX/CMP: This stores how many classes the model that was run can emit, as resolved from the model's checkpoint.
    confidence_threshold REAL NOT NULL, -- CODEX/CMP: Confidence threshold for model outputs, as specified in the configuration files (model's .conf, optionally overwritten by teacup/model.conf).
    confidence_threshold_source TEXT NOT NULL CHECK(confidence_threshold_source IN ('model_checkpoint', 'model_settings_file', 'folder_settings_file')), -- CODEX/CMP: Keep track of how/where the threshold was specified. 'model_checkpoint' should only be specified by Teacup when the threshold actually comes from an authoritative checkpoint field.
    preprocessing_json TEXT NOT NULL, -- CODEX/CMP: Records image preparation used before inference, such as RGB conversion, square resize, etc.
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

/* CODEX/CMP: Store Teacup's annotation classes for a given project/folder. Each row is a stable semantic class that users can assign
   to annotations, audit over time, export, recolour, or keep as a Teacup-internal category such as arrows. Model-specific raw class IDs
   do not live here because the same semantic class can be emitted under different indices by different checkpoints.*/
CREATE TABLE annotation_classes (
    class_id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_uuid TEXT NOT NULL UNIQUE,          -- CODEX: Adds a durable class identifier for audit records and exports.
    class_name TEXT NOT NULL UNIQUE,
    class_list_order INTEGER NOT NULL UNIQUE, -- CODEX: Replaces current class_index; this is only Teacup's class-list order, while model-facing class indices live in model_run_classes.
    annotation_family TEXT NOT NULL CHECK(annotation_family IN ('region', 'keypoints')),
    class_source TEXT NOT NULL CHECK(class_source IN ('manual', 'model', 'import', 'teacup_internal')), -- CODEX/CMP: Records where the class first came from: manual entry, model output, import data, or Teacup-managed internal classes such as arrows.
    supercategory TEXT,
    display_color TEXT,
    keypoint_labels_json TEXT NOT NULL DEFAULT '[]', -- CODEX: Defines ordered keypoint names for keypoint annotations; arrows can use ["base", "tip"].
    session_id TEXT NOT NULL,                         -- CODEX: Records where the class was first entered; edits are recorded in audit_event_classes.
    entry_time INTEGER NOT NULL,                      -- CODEX: Records class creation time without requiring audit replay.
    source_reference TEXT,                            -- CODEX: Replaces source_setting_key with a clearer source pointer, such as manual entry, model path, or settings file key.
    coco_category_id INTEGER UNIQUE NOT NULL, -- CODEX: COCO/interchange category id preserved from imported COCO when available or assigned by Teacup for export; this is not a model class index.
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);


/* CODEX/CMP: This table is necessary because different models run on the same folder are not guaranteed to have the same class/ID mappings.
   The include_in_model_import also enables selective loading of model classes as annotations into Teacup. */
CREATE TABLE model_run_classes (
    model_run_class_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_run_class_uuid TEXT NOT NULL UNIQUE, -- CODEX/CMP: Adds durable class identifier for model checkpoint-specific class mappings as well (see annotation_classes).
    model_run_id INTEGER NOT NULL,
    model_class_index INTEGER NOT NULL, -- CODEX: Stores the raw class index from one specific model checkpoint; this value is not globally meaningful across models.
    model_class_name TEXT NOT NULL,     -- CODEX: Stores the raw class name reported by the checkpoint for audit and debugging.
    class_id INTEGER,          -- CODEX/CMP: Optional current link from model-specific output to Teacup's stable semantic class; model classes that are not reviewable should not be forced to have a class binding.
    include_in_model_import INTEGER NOT NULL DEFAULT 1 CHECK(include_in_model_import IN (0, 1)), -- CODEX/CMP: Record policy for whether model outputs belonging to this class are loaded into Teacup for a specific run for review.
    UNIQUE(model_run_id, model_class_index),
    FOREIGN KEY(model_run_id) REFERENCES model_runs(model_run_id) ON DELETE CASCADE,
    FOREIGN KEY(class_id) REFERENCES annotation_classes(class_id) ON DELETE SET NULL -- CODEX: Model-run class rows outlive project class rows so benchmarking can still inspect raw checkpoint classes even after a Teacup class is deleted.
    -- CODEX/CMP: Authoritative per-run mapping. Separates model vocabulary from project vocabulary so model A class 2 and model B class 0 can both map to the same Teacup class.
);


/* CODEX/CMP: Authoritative annotation store. */
CREATE TABLE annotations (
    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    annotation_uuid TEXT NOT NULL UNIQUE, -- CODEX/CMP: Absorbs arrow_uuid into the generic annotation identity.
    image_id INTEGER NOT NULL,
    class_id INTEGER NOT NULL, -- CODEX: Current Teacup semantic class assigned to this annotation.
    session_id TEXT NOT NULL,
    model_run_class_id INTEGER, -- CODEX: Set when/if the annotation was created from model output; records the raw model class mapping that produced the annotation, even if class_id is later corrected by the user.
    entry_time INTEGER NOT NULL,
    annotation_type TEXT NOT NULL CHECK(annotation_type IN ('polygon', 'rectangle', 'keypoints')),
    annotation_role TEXT NOT NULL DEFAULT '', -- CODEX: Adds a subtype marker; arrows are keypoint annotations with role 'arrow'.
    annotation_order INTEGER NOT NULL, -- CODEX/CMP: Preserves the image-local order of annotations as Teacup loads, draws, hit-tests, and exports them; this replaces implicit row-order dependence.
    geometry_json TEXT NOT NULL,              -- CODEX: Replaces legacy polygon_coords and stores the authoritative polygon, rectangle, or keypoint geometry in one annotation table.
    model_confidence REAL, -- CODEX: Optional confidence score for model-created annotations; exported back to COCO as score when present.
    annotation_source TEXT NOT NULL CHECK(annotation_source IN ('manual', 'model', 'import', 'teacup_internal')),            -- CODEX: Replaces legacy entry_type with clearer provenance wording.
    metadata_json TEXT NOT NULL DEFAULT '{}',  -- CODEX: Stores optional annotation extension metadata for import/export.
    UNIQUE(image_id, annotation_order), -- CODEX/CMP: Enforce unique so that two annotations cannot claim the same order.
    CHECK(annotation_source != 'model' OR model_run_class_id IS NOT NULL), -- CODEX/CMP: Ensure model provenance is guaranteed by the database.
    FOREIGN KEY(image_id) REFERENCES project_images(image_id) ON DELETE CASCADE,
    FOREIGN KEY(class_id) REFERENCES annotation_classes(class_id),
    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
    FOREIGN KEY(model_run_class_id) REFERENCES model_run_classes(model_run_class_id)
);

/* CODEX/CMP: Store project vocabulary for audit actions. This makes action names inspectable schema data instead of
   free-text strings embedded only in the audit_event rows. This enables a place to document action meanings,
   retire old names and keep historical rows interpretable. For example, if draw_arrow later becomes create_keypoint_annot,
   old events can keep pointing to the original action row, while retired_app_version and action_description explain the
   transition. */
CREATE TABLE audit_event_actions (
    audit_event_action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_key TEXT NOT NULL UNIQUE, -- CODEX: Stable machine key for the action, such as create_annotation or move_vertex.
    action_label TEXT NOT NULL, -- CODEX: Human-readable action name for reports and audit displays.
    action_description TEXT, -- CODEX: Optional explanation of what the action means in this schema/application version.
    introduced_app_version TEXT, -- CODEX: Teacup version that introduced this action key when known.
    retired_app_version TEXT -- CODEX: Teacup version that stopped writing this action key; NULL while active.
);


/* CODEX/CMP: Store individual events (e.g., merges, deletes, etc). Since these events may affect multiple annotations,
   a separate table is necessary for each affected annotation. */
CREATE TABLE audit_events (
    audit_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_event_uuid TEXT NOT NULL UNIQUE, -- CODEX: Durable event identified for JSON backups, exports, debugging...
    session_id TEXT NOT NULL,
    event_completed_time_ms INTEGER NOT NULL, -- CODEX/CMP: Store in UTC milliseconds.
    duration_ms INTEGER, -- CODEX: Elapsed interaction time for this audit event when Teacup measured one; NULL otherwise (e.g., image view events).
    undo_of_audit_event_id INTEGER, -- CODEX: Set only for undo events; references the audit event whose user-visible effect this event reverses.
    audit_event_action_id INTEGER NOT NULL, -- CODEX/CMP: Reference to database-recorded action vocabulary.
    event_summary TEXT, -- CODEX/CMP: Optional human-readable summary for logs, diagnostics, or export review.
    details_json TEXT NOT NULL DEFAULT '{}', -- CODEX/CMP: Optional structured event metadata for facts that belong to the action as a whole, such as image name, resampling method.
    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
    FOREIGN KEY(undo_of_audit_event_id) REFERENCES audit_events(audit_event_id), -- CODEX: Keeps undo provenance tied to an event that exists in this audit log.
    FOREIGN KEY(audit_event_action_id) REFERENCES audit_event_actions(audit_event_action_id)
);

/* CODEX/CMP: Records which annotation rows were affected by an event. This table makes multi-annotation events queryable
   without duplicating event-level fields. */
CREATE TABLE audit_event_annotations (
    audit_event_id INTEGER NOT NULL,
    annotation_uuid TEXT NOT NULL, -- CODEX: References the durable annotation identity rather than only the live row id so deleted annotations remain traceable.
    change_type TEXT NOT NULL CHECK(change_type IN ('created', 'updated', 'deleted')),
    before_state_json TEXT, -- CODEX: Optional annotation snapshot before the event; NULL when the annotation did not exist before this event.
    after_state_json TEXT, -- CODEX/CMP: Optional annotation snapshot after the event.
    CHECK(
        (change_type = 'created' AND before_state_json IS NULL AND after_state_json IS NOT NULL)
        OR (change_type = 'updated' AND before_state_json IS NOT NULL AND after_state_json IS NOT NULL)
        OR (change_type = 'deleted' AND before_state_json IS NOT NULL AND after_state_json IS NULL)
    ), -- CODEX: Enforce the snapshots needed to reconstruct each annotation change type.
    PRIMARY KEY(audit_event_id, annotation_uuid),
    FOREIGN KEY(audit_event_id) REFERENCES audit_events(audit_event_id) ON DELETE CASCADE
    -- CODEX/CMP: Replaces separate legacy audit_event_annotations/audit_event_arrows handling with one generic annotation audit table.
);

/* CODEX/CMP: Records which project classes were affected by an event. Class changes are audited separately from annotation changes
   because class names, colours, source, and import policy can change even when no annotation geometry changes. */
CREATE TABLE audit_event_classes (
    audit_event_id INTEGER NOT NULL,
    class_uuid TEXT NOT NULL, -- CODEX: References the durable project-class identity so class history remains readable if the live row is later removed.
    change_type TEXT NOT NULL CHECK(change_type IN ('created', 'updated', 'deleted')),
    before_state_json TEXT, -- CODEX/CMP: Optional class snapshot before the event; NULL when the class did not exist before this event.
    after_state_json TEXT, -- CODEX/CMP: Optional class snapshot after the event; NULL when the class was deleted by this event.
    CHECK(
        (change_type = 'created' AND before_state_json IS NULL AND after_state_json IS NOT NULL)
        OR (change_type = 'updated' AND before_state_json IS NOT NULL AND after_state_json IS NOT NULL)
        OR (change_type = 'deleted' AND before_state_json IS NOT NULL AND after_state_json IS NULL)
    ), -- CODEX: Enforce the snapshots needed to reconstruct class changes after class rows are deleted.
    PRIMARY KEY(audit_event_id, class_uuid),
    FOREIGN KEY(audit_event_id) REFERENCES audit_events(audit_event_id) ON DELETE CASCADE
    -- CODEX: Adds explicit audit coverage for annotation class creation, renaming, remapping, deletion, and display changes.
);

/*
CODEX: coco_info preserves the top-level COCO info object across SQLite
       round trips. It is export/import metadata, not Teacup preferences,
       model configuration, audit state, or README project metadata.
*/
CREATE TABLE coco_info (
    coco_info_id INTEGER PRIMARY KEY CHECK(coco_info_id = 1), -- CODEX: Singleton row id; one Teacup project database has one COCO info object.
    info_json TEXT NOT NULL DEFAULT '{}', -- CODEX: Serialized COCO top-level info dictionary preserved for COCO exports.
    updated_time INTEGER NOT NULL -- CODEX/CMP: Store UTC Unix seconds.
);

CREATE INDEX idx_project_images_flags ON project_images(marked_for_deletion, moved_to_trash);
CREATE INDEX idx_annotations_class ON annotations(class_id);
CREATE INDEX idx_annotations_model_run_class ON annotations(model_run_class_id);
CREATE INDEX idx_audit_events_session_time ON audit_events(session_id, event_completed_time_ms);
CREATE INDEX idx_audit_event_annotations_uuid ON audit_event_annotations(annotation_uuid, audit_event_id);
CREATE INDEX idx_audit_event_classes_uuid ON audit_event_classes(class_uuid, audit_event_id);
