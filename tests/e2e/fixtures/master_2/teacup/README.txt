[project]
author_name = c
author_email = a
author_primary_affiliation = d
project_name = e
dataset_version = f
dataset_identifier = fg
data_license = sdf
source_image_origin = sdf
source_image_rights = sdf
model_identifier = sdf
model_access_and_license = sdf
project_description = sdf
collection_methodology = sdf
annotation_methodology = sdf
quality_control_methodology = sdfsdf

[provenance]
last_save_date_time = 2026-08-25T14:44:36-07:00
annotator_name = Teacup Annotator
annotator_version = 0.9.8
annotator_zenodo_doi = not yet assigned

[files]
teacup/README.txt = Project, provenance, and file metadata.
teacup/Teacup.sqlite3 = Authoritative annotation database.
annotations.json = Complete optional COCO JSON backup and recovery source.
teacup/annotations_polygons.json = Optional polygon-only COCO JSON export.
teacup/annotations_rectangles.json = Optional rectangle-only COCO JSON export.
teacup/model.conf = Folder model weights, threshold, class order, and default class.
teacup/classes.json = Folder annotation class names and display colours.
teacup/audit_events.jsonl = Optional human-readable annotation audit backup.
teacup/deletion_marks.json = Images marked for deletion on the next confirmed save.
*.jpg / *.jpeg = Source images loaded for annotation.
teacup/pi_json/<image-filename>.json = Optional per-image annotation backup files.
