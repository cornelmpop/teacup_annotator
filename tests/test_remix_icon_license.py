"""Tests for bundled Remix Icon provenance and license packaging."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tomllib
import unittest


LICENSE_PATH = Path("annotator/icons/REMIX_ICON_LICENSE.txt")
LICENSE_SHA256 = "6f2f21c5f8db34635d31848e9ff831d5dc421bb83ffc9d37f82651364047ae58"


class RemixIconLicenseTests(unittest.TestCase):
    """Remix toolbar assets retain pinned provenance and distribution terms."""

    def test_bundled_license_matches_remix_icon_v4_9_1(self) -> None:
        """The notice is the exact license published for the chosen release."""

        license_digest = sha256(LICENSE_PATH.read_bytes()).hexdigest()

        self.assertEqual(license_digest, LICENSE_SHA256)

    def test_build_metadata_packages_remix_license(self) -> None:
        """Both license metadata and package data include the third-party terms."""

        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn(
            "annotator/icons/REMIX_ICON_LICENSE.txt",
            pyproject["project"]["license-files"],
        )
        self.assertIn(
            "icons/REMIX_ICON_LICENSE.txt",
            pyproject["tool"]["setuptools"]["package-data"]["annotator"],
        )

    def test_icon_readme_records_provenance_and_asset_mapping(self) -> None:
        """The notice identifies the upstream release and every covered PNG."""

        readme_lines = Path("annotator/icons/README.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        nonempty_lines = [line for line in readme_lines if line]
        expected_assets = (
            "- archive.png: Business / archive-line",
            "- config.png: System / settings-5-line",
            "- delete.png: System / delete-bin-line",
            "- flag.png: Business / flag-line",
            "- flag_off.png: Business / flag-off-line",
            "- load.png: Document / folder-open-line",
            "- reset_zoom.png: Media / aspect-ratio-line",
            "- restore.png: Device / device-recover-line",
            "- run.png: User & Faces / robot-2-line",
            "- save.png: Device / save-3-line",
        )

        self.assertEqual(
            nonempty_lines[:3],
            [
                "https://remixicon.com",
                "June–August 2026",
                "Remix Icon v4.9.1",
            ],
        )
        self.assertIn("License: Remix Icon License v1.0", nonempty_lines)
        self.assertIn("License text: REMIX_ICON_LICENSE.txt", nonempty_lines)
        for asset_entry in expected_assets:
            with self.subTest(asset_entry=asset_entry):
                self.assertIn(asset_entry, nonempty_lines)
        self.assertEqual(
            nonempty_lines[-1],
            "These files are functional interface components and are not "
            "Teacup branding.",
        )


if __name__ == "__main__":
    unittest.main()
