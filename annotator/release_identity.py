"""Expose Teacup Annotator's shared release identity.

The package version itself comes from installed `teacup-annotator` metadata;
this module centralizes the app id, display name, provenance DOI placeholder,
and backend-version policy used by GUI, CLI, preferences, SQLite sessions, and
project metadata.
"""

from importlib.metadata import version


APP_ID = "teacup-annotator"
APP_NAME = "Teacup Annotator"
APP_VERSION = version(APP_ID)
APP_ZENODO_DOI = "not yet assigned"
BACKEND_VERSION = APP_VERSION
