from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import convert_to_wp


HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <title>Sample</title>
  <link
    rel="stylesheet"
    href="./dist/css/main.css"
  />
</head>
<body class="t-website p-home">
  <header class="site-header">
    <a
      href="./index.html"
      class="site-title__link"
    >
      Sample
    </a>
  </header>

  <main class="site-main">
    <h1>Sample</h1>
  </main>

  <footer class="site-footer">
    <a href="./contact.html">Contact</a>
  </footer>

  <script
    type="module"
    src="./dist/js/core/app.js"
  ></script>
</body>
</html>
"""


class ConversionSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.base_dir = self.root / "project-generator"
        self.project_dir = (
            self.base_dir
            / "outputs"
            / "sample"
        )
        self.project_dir.mkdir(parents=True)

        wp_stubs_dir = self.base_dir / "wp-stubs"
        wp_stubs_dir.mkdir()

        (wp_stubs_dir / "style.css").write_text(
            "/*\nTheme Name: Project\n*/\n",
            encoding="utf-8",
        )
        (wp_stubs_dir / "index.php").write_text(
            "<?php\n",
            encoding="utf-8",
        )

        for html_name in (
            "index.html",
            "about.html",
            "service.html",
            "contact.html",
        ):
            (self.project_dir / html_name).write_text(
                HTML_TEMPLATE,
                encoding="utf-8",
            )

        (self.project_dir / "keep.txt").write_text(
            "keep\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def assert_no_transaction_directories(self) -> None:
        leftovers = [
            path.name
            for path in self.project_dir.parent.iterdir()
            if path.name.startswith(".sample.wp-tmp-")
            or path.name.startswith(".sample.wp-backup-")
        ]

        self.assertEqual([], leftovers)

    def ownership_manifest_path(
        self,
    ) -> Path:
        return (
            self.project_dir
            / (
                convert_to_wp
                .WP_OWNERSHIP_MANIFEST_FILENAME
            )
        )

    def read_ownership_manifest(
        self,
    ) -> dict:
        return json.loads(
            self.ownership_manifest_path()
            .read_text(
                encoding="utf-8"
            )
        )

    def write_ownership_manifest(
        self,
        manifest: dict,
    ) -> None:
        self.ownership_manifest_path()
        self.ownership_manifest_path().write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_initial_conversion_succeeds_without_force(
        self,
    ) -> None:
        project_dir, generated_files = (
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
            )
        )

        self.assertEqual(
            self.project_dir,
            project_dir,
        )
        self.assertIn(
            "functions.php",
            generated_files,
        )
        self.assertTrue(
            (
                self.project_dir
                / "front-page.php"
            ).is_file()
        )
        self.assertEqual(
            "keep\n",
            (
                self.project_dir
                / "keep.txt"
            ).read_text(
                encoding="utf-8"
            ),
        )

        manifest = (
            self.read_ownership_manifest()
        )

        self.assertEqual(
            1,
            manifest["schemaVersion"],
        )
        self.assertEqual(
            (
                convert_to_wp
                .WP_OWNERSHIP_MANIFEST_KIND
            ),
            manifest["kind"],
        )
        self.assertEqual(
            "website",
            manifest["template"],
        )

        records = {
            record["path"]:
            record["sha256"]
            for record
            in manifest["generatedFiles"]
        }

        self.assertEqual(
            set(generated_files),
            set(records),
        )

        for path, expected_hash in (
            records.items()
        ):
            self.assertEqual(
                expected_hash,
                convert_to_wp.sha256_file(
                    self.project_dir
                    / path
                ),
            )

        self.assert_no_transaction_directories()

    def test_existing_generated_files_require_force(
        self,
    ) -> None:
        existing_file = (
            self.project_dir
            / "functions.php"
        )
        existing_file.write_text(
            "old\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            "--force",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
            )

        self.assertEqual(
            "old\n",
            existing_file.read_text(
                encoding="utf-8"
            ),
        )
        self.assert_no_transaction_directories()

    def test_force_failure_preserves_existing_project(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        existing_file = (
            self.project_dir
            / "functions.php"
        )
        original_content = (
            existing_file.read_text(
                encoding="utf-8"
            )
        )
        original_manifest = (
            self.ownership_manifest_path()
            .read_text(
                encoding="utf-8"
            )
        )

        with patch.object(
            convert_to_wp,
            "generate_wp_stub_files",
            side_effect=OSError(
                "stub generation failed"
            ),
        ):
            with self.assertRaisesRegex(
                OSError,
                "stub generation failed",
            ):
                convert_to_wp.convert_project(
                    base_dir=self.base_dir,
                    project_name="sample",
                    template_name="website",
                    force=True,
                )

        self.assertEqual(
            original_content,
            existing_file.read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            original_manifest,
            self.ownership_manifest_path()
            .read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            "keep\n",
            (
                self.project_dir
                / "keep.txt"
            ).read_text(
                encoding="utf-8"
            ),
        )
        self.assert_no_transaction_directories()

    def test_force_success_replaces_generator_owned_files(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        stale_file = (
            self.project_dir
            / "page-products.php"
        )
        stale_file.write_text(
            "stale generator output\n",
            encoding="utf-8",
        )

        manifest = (
            self.read_ownership_manifest()
        )
        manifest["generatedFiles"].append(
            {
                "path": "page-products.php",
                "sha256": (
                    convert_to_wp.sha256_file(
                        stale_file
                    )
                ),
            }
        )
        self.write_ownership_manifest(
            manifest
        )

        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
            force=True,
        )

        self.assertFalse(
            stale_file.exists()
        )

        refreshed_manifest = (
            self.read_ownership_manifest()
        )
        refreshed_paths = {
            record["path"]
            for record
            in refreshed_manifest[
                "generatedFiles"
            ]
        }

        self.assertNotIn(
            "page-products.php",
            refreshed_paths,
        )
        self.assertEqual(
            "keep\n",
            (
                self.project_dir
                / "keep.txt"
            ).read_text(
                encoding="utf-8"
            ),
        )
        self.assert_no_transaction_directories()

    def test_page_class_for_html_name(self) -> None:
        self.assertEqual(
            "p-home",
            convert_to_wp.page_class_for_html_name(
                "index.html"
            ),
        )
        self.assertEqual(
            "p-about",
            convert_to_wp.page_class_for_html_name(
                "about.html"
            ),
        )
        self.assertEqual(
            "p-products",
            convert_to_wp.page_class_for_html_name(
                "products.html"
            ),
        )

    def test_force_rejects_untracked_generated_filename(
        self,
    ) -> None:
        existing_file = (
            self.project_dir
            / "functions.php"
        )
        existing_file.write_text(
            "user file\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            "所有権",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
                force=True,
            )

        self.assertEqual(
            "user file\n",
            existing_file.read_text(
                encoding="utf-8"
            ),
        )
        self.assertFalse(
            self.ownership_manifest_path()
            .exists()
        )
        self.assert_no_transaction_directories()

    def test_force_rejects_modified_owned_file(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        functions_path = (
            self.project_dir
            / "functions.php"
        )
        functions_path.write_text(
            "<?php\n// user modification\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            "変更された",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
                force=True,
            )

        self.assertEqual(
            "<?php\n// user modification\n",
            functions_path.read_text(
                encoding="utf-8"
            ),
        )
        self.assert_no_transaction_directories()

    def test_force_recreates_missing_owned_file(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        page_path = (
            self.project_dir
            / "page-about.php"
        )
        page_path.unlink()

        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
            force=True,
        )

        self.assertTrue(
            page_path.is_file()
        )
        self.assert_no_transaction_directories()

    def test_force_rejects_tampered_ownership_path(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        manifest = (
            self.read_ownership_manifest()
        )
        manifest["generatedFiles"][0][
            "path"
        ] = "../outside.php"
        self.write_ownership_manifest(
            manifest
        )

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            "管理範囲外",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
                force=True,
            )

        self.assert_no_transaction_directories()

    def test_generated_pages_register_expected_body_classes(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        expected_classes = {
            "front-page.php": "p-home",
            "page-about.php": "p-about",
            "page-service.php": "p-service",
            "page-contact.php": "p-contact",
        }

        for php_name, expected_class in (
            expected_classes.items()
        ):
            with self.subTest(php_name=php_name):
                php = (
                    self.project_dir
                    / php_name
                ).read_text(encoding="utf-8")

                self.assertIn(
                    (
                        "$classes[] = "
                        f"'{expected_class}';"
                    ),
                    php,
                )

        header_php = (
            self.project_dir
            / "header.php"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "body_class('t-website')",
            header_php,
        )

    def test_missing_stub_preserves_project(self) -> None:
        (
            self.base_dir
            / "wp-stubs"
            / "style.css"
        ).unlink()

        with self.assertRaises(
            convert_to_wp.ConversionError
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
            )

        self.assertEqual(
            "keep\n",
            (self.project_dir / "keep.txt").read_text(
                encoding="utf-8"
            ),
        )
        self.assertFalse(
            (self.project_dir / "functions.php").exists()
        )
        self.assert_no_transaction_directories()

    def test_swap_failure_restores_original_directory(self) -> None:
        staging_dir = (
            self.project_dir.parent
            / ".sample.wp-tmp-manual"
        )
        staging_dir.mkdir()

        (staging_dir / "replacement.txt").write_text(
            "replacement\n",
            encoding="utf-8",
        )

        original_rename = Path.rename

        def rename_with_failure(
            path: Path,
            target: Path,
        ) -> Path:
            if (
                path == staging_dir
                and target == self.project_dir
            ):
                raise OSError("swap failed")

            return original_rename(
                path,
                target,
            )

        with patch.object(
            Path,
            "rename",
            new=rename_with_failure,
        ):
            with self.assertRaisesRegex(
                OSError,
                "swap failed",
            ):
                convert_to_wp.replace_directory_transactionally(
                    staging_dir,
                    self.project_dir,
                )

        self.assertTrue(self.project_dir.is_dir())
        self.assertEqual(
            "keep\n",
            (self.project_dir / "keep.txt").read_text(
                encoding="utf-8"
            ),
        )

        backup_directories = [
            path
            for path in self.project_dir.parent.iterdir()
            if path.name.startswith(".sample.wp-backup-")
        ]

        self.assertEqual([], backup_directories)


if __name__ == "__main__":
    unittest.main()
