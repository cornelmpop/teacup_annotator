# Teacup Annotator
[![Tests](https://github.com/cornelmpop/teacup_annotator/actions/workflows/tests.yml/badge.svg)](https://github.com/cornelmpop/teacup_annotator/actions/workflows/tests.yml)

Teacup Annotator is a cross-platform, lightweight desktop image annotation tool
with support for creating, editing, classifying, and auditing manual or
model-generated polygon or rectangle annotations. It was written to enable
fast and efficient human validation, benchmarking, and a series of annotation
operations that are not typically supported by lightweight annotation tools,
such as shared-boundary topological editing (e.g., dorsal scars for stone
tools) and vertex ordering.

## Main Features
Some of the main features include:

1. Support for RF-DETR object detection and segmentation models.
2. Efficient cleaning of model outputs through:
   - Increased error salience:
     + Additive colours increase the visual salience of overlapping polygons,
       including those belonging to the same class.
     + Hover labels and optional fixed display of class labels on annotations.
     + Per-image class counts to increase visibility of class assignment errors.
     + Optional shared-edge and shared-vertex highlighting.
   - Fast geometric corrections for individual annotations:
     + Multi-vertex selection for efficient bulk vertex removal
     + Outline resampling to simplify overly detailed polygon outlines
     + Live zoom preview for fast (i.e., no need to zoom in and out) and
       precise main canvas actions (e.g., moving a vertex).
     + Optional vertex snapping.
   - Fast multi-annotation corrections:
     + Overlap-aware delete operations optimized for quick deletion of false
       positives in crowded areas (through a size-ordered sub-menu).
     + Group selection (region-based or individual annotation selection) that
       enables bulk reclassification, deletion, merges, and resampling.
   - Reclassification and manual addition of missed objects.
3. Efficient navigation:
   - Flagging of problematic cases for later review
   - Review filtering (by classes, annotation status, and flagged status)
4. Auditability and reproducibility:
   - Manual, imported, and reproducible model-generated annotations are
     distinguished.
   - Source-aware re-runs: another model run will not re-write human annotations
     and model annotations remain traceable to individual models and
     inference parameters.
   - Audited and time-stamped navigation and edit events enable protocol-based
     benchmarking of model output against reviewed human corrections, and
     analysis of human correction burden.
5. Support for FAIR compatible workflows and outputs:
   - Use of open formats, plain-text outputs, and a simple folder-first
     project model: SQLite backend with plain-text backups for permanent
     storage, with all project files stored in a single top-level folder.
   - Unified storage: project information, image collection, annotations, and
     metadata are all stored in the same working directory.
   - Archive functionality that encourages good practices, including
     human-authored class definitions, verifiable integrity for every archive
     member, synchronized SQLite snapshot and COCO JSON output, and
     preventing distribution of data with major methodology and rights fields
     absent.
   - Image-identity and folder reconciliation: checksum identity checks,
     added/missing image reconciliation, deletion state, and controlled
     restoration.
   - Full audit trail for all state-changing annotation operations.
   - Use of uv.lock files for reproducibility: keeps track of the software
     environment.
6. Special annotations and annotation modes:
   - A 'turtle-shell' model that enables creating and editing annotations with
     shared-boundary topology.
   - Arrows as a special annotation class (useful, for instance, for defining
     direction of removal for dorsal scars on stone tools).
   - Vertex reordering (useful for setting a standardized starting point for
     annotation outlines)
7. Simple and portable:
   - Local, account-free, multi-platform desktop operation suitable for
     working with sensitive or offline datasets.
   - COCO JSON import and export facility, SQLite authoritative backend.
   - Simple installation, simple interface.
   - Designed to minimize required mouse movements: all major repetitive
     operations can be performed through customizable keyboard shortcuts
     or contextual right-click menu actions (i.e., there is no need to
     navigate to different parts of the user interface).
   - Remembered folder and image position: Allows restarting a previous
     session with minimal friction.
   - Annotation crop exports to facilitate model training.

## Limitations

Current limitations include:

1. Only JPEG images are supported.
2. All images must be in the top-level folder (i.e., you can't store images
   in sub-folders).
3. Arrow annotations are not exported to COCO.
4. Archives are not encrypted or anonymized; they may contain private
   information such as host names and local filesystem paths.
5. Only RF-DETR models are supported.
6. Model runs affect the entire project - there is currently no support for
   per-image runs
7. COCO JSON import limitation: only one exterior outline per region is
   supported (i.e., no disconnected components or interior holes). Multi-part
   regions are combined during import into one editable outline - disconnected
   parts use their convex hull, and holes are flattened. Rows with unusable IDs,
   unknown image IDs, or no supported editable geometry are omitted. Note that
   detected conversions and rejected rows are written to
   `last_coco_import_report.txt` beside the platform's `annotator_prefs.conf`.
   A clean import will replace that file with a no-changes report.

## Status And Supported Environment

Teacup Annotator is under active development, and this version (0.9.8) is best
described as a fully functional pilot/preview. While the JSON import/export
behaviour is not expected to change, the overall architecture may, so be aware
that current projects may be incompatible with future versions of the software.

For the current version the supported environment is:

- Python 3.11, 3.12, or 3.13.
- A Python build with Tk support.
- macOS or Windows (Linux should work too, but it is untested at the moment).
- A checked-out source tree managed by `uv`, or an installed wheel/sdist
  built from this project.

The installed application command is `teacup-annotator`. The Python import
package remains `annotator`, because hyphenated names are not importable Python
packages.

## Quick Start

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/), then
run:

```console
uv sync --locked
uv run teacup-annotator
```

The first command creates `.venv`, installs the application as an editable
package, and installs the core dependency set recorded in `uv.lock`.

For RF-DETR inference:

```console
uv sync --locked --extra model
uv run teacup-annotator
```

For lithic illustration extraction, you may want to try three fine-tuned
RF-DETR models available here: [Zenodo record](https://doi.org/10.5281/zenodo.23051990)


## Documentation

Detailed documentation is forthcoming. Two important usage aspects are
briefly noted below.

### Project Data

Each loaded image folder is a project. Important files include:

- `annotations.json`: optional complete COCO backup and interchange file at
  the project root beside the source images.
- `teacup/Teacup.sqlite3`: authoritative annotations, classes, audit events,
  session identity, model provenance, review flags, and deletion state.
- `teacup/audit_events.jsonl`: optional audit backup whose current rows include
  the complete session record needed to restore their SQLite foreign key.
- `teacup/README.txt`: project, author, rights, methodology, and provenance
  metadata.
- `teacup/pi_json/<image-filename>.json`: optional per-image backup retaining
  `.jpg` or `.jpeg` in its name.
- `teacup/statistics/`: derived per-session timing summaries.
- `teacup/model.conf`: optional folder model settings.
- `teacup/classes.json`: ordered class names and display colours.
- `teacup/crops/`: cropped annotation images and associated annotations.json,
  created on save. Don't save anything else in that folder.
- `teacup/trash/`: images moved from the main project folder on delete.
- `teacup/class_definitions.txt`: A class definition file that must be created
  by the user and is required for archiving.

Teacup allows one loaded application owner per project. SQLite retains an
operating-system-backed exclusive lock until that project connection closes,
so a second Teacup instance receives SQLite's lock error instead of saving a
stale in-memory document over newer annotations.

### Privacy And Distribution

Distribution archives contain the source JPEGs, a SQLite snapshot, generated
COCO annotations, project metadata, class definitions, and checksums. They are
not encrypted or anonymized. Images may retain EXIF metadata, and SQLite may
contain host information, absolute paths, session identifiers, timestamps,
audit history, and model provenance.

## License

Teacup Annotator is licensed under the GNU General Public License, version 2
or any later version (`GPL-2.0-or-later`). See [LICENSE](LICENSE).

The ten toolbar icons identified in
[`annotator/icons/README.txt`](annotator/icons/README.txt) are from Remix Icon
v4.9.1 and remain separately governed by the Remix Icon License v1.0. They are
functional interface components, not Teacup branding. See
[`annotator/icons/REMIX_ICON_LICENSE.txt`](annotator/icons/REMIX_ICON_LICENSE.txt)
for the applicable terms.

Third-party libraries, model packages, and model weights retain their own
licenses. In particular, supported open RF-DETR components are separate
Apache-2.0 works; RF-DETR Plus components use different terms and are not
supported.
