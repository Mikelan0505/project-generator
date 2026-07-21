from __future__ import annotations

import json
import tempfile
import unittest
import warnings
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

        self.write_generation_manifest(
            "website"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def assert_no_transaction_directories(self) -> None:
        self.assertEqual(
            (),
            convert_to_wp.filesystem_safety
            .find_project_transaction_artifacts(
                self.project_dir
            ),
        )

    def generation_manifest_path(
        self,
    ) -> Path:
        return (
            self.project_dir
            / "project-manifest.json"
        )

    def write_generation_manifest(
        self,
        template_name: str,
    ) -> None:
        self.generation_manifest_path().write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "project": {
                        "template": template_name,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def project_snapshot(
        self,
    ) -> dict[str, bytes]:
        return {
            path.relative_to(
                self.project_dir
            ).as_posix(): path.read_bytes()
            for path in sorted(
                self.project_dir.rglob("*")
            )
            if path.is_file()
        }

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

    def test_initial_conversion_rejects_generation_template_mismatch(
        self,
    ) -> None:
        before = self.project_snapshot()

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            (
                "project=sample"
                ".*generation=website"
                ".*requested=shop"
            ),
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="shop",
            )

        self.assertEqual(
            before,
            self.project_snapshot(),
        )
        self.assert_no_transaction_directories()

    def test_conversion_requires_valid_generation_manifest(
        self,
    ) -> None:
        for invalid_content in (
            None,
            "{ invalid json\n",
        ):
            with self.subTest(
                invalid_content=invalid_content
            ):
                self.write_generation_manifest(
                    "website"
                )

                if invalid_content is None:
                    self.generation_manifest_path().unlink()
                else:
                    self.generation_manifest_path().write_text(
                        invalid_content,
                        encoding="utf-8",
                    )

                before = self.project_snapshot()

                with self.assertRaisesRegex(
                    convert_to_wp.ConversionError,
                    "generation manifest",
                ):
                    convert_to_wp.convert_project(
                        base_dir=self.base_dir,
                        project_name="sample",
                        template_name="website",
                    )

                self.assertEqual(
                    before,
                    self.project_snapshot(),
                )
                self.assert_no_transaction_directories()

    def test_force_rejects_requested_template_mismatch(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )
        before = self.project_snapshot()

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            "generation=website.*requested=shop",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="shop",
                force=True,
            )

        self.assertEqual(
            before,
            self.project_snapshot(),
        )
        self.assert_no_transaction_directories()

    def test_force_rejects_ownership_template_mismatch(
        self,
    ) -> None:
        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )
        manifest = self.read_ownership_manifest()
        manifest["template"] = "shop"
        self.write_ownership_manifest(
            manifest
        )
        before = self.project_snapshot()

        with self.assertRaisesRegex(
            convert_to_wp.ConversionError,
            "ownership=shop.*requested=website",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
                force=True,
            )

        self.assertEqual(
            before,
            self.project_snapshot(),
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

    def test_navigation_current_state_is_dynamic_and_nav_scoped(
        self,
    ) -> None:
        source = """
<nav class="site-nav">
  <a href="./index.html" class="is-current" aria-current="page">Top</a>
  <a href="./products.html">Products</a>
  <a href="./contact.html" class="site-nav__cta">Contact</a>
</nav>
<a href="./products.html">Outside navigation</a>
"""

        result = (
            convert_to_wp
            .rewrite_navigation_current_state(
                source,
                home_url_map={
                    "index.html": "home",
                    "products.html": (
                        "products"
                    ),
                    "contact.html": (
                        "contact"
                    ),
                },
            )
        )

        self.assertIn(
            "is_front_page()",
            result,
        )
        self.assertIn(
            "is_page( 'products' )",
            result,
        )
        self.assertIn(
            "is_page( 'contact' )",
            result,
        )
        self.assertIn(
            (
                "site-nav__cta"
                "<?php echo "
                "is_page( 'contact' )"
                " ? ' is-current' : ''; ?>"
            ),
            result,
        )
        self.assertIn(
            'aria-current="page"',
            result,
        )
        self.assertIn(
            (
                '<a href="./products.html">'
                "Outside navigation</a>"
            ),
            result,
        )

    def test_generated_navigation_uses_wordpress_current_conditions(
        self,
    ) -> None:
        navigation_html = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <title>Navigation Sample</title>
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

    <nav
      class="site-nav"
      aria-label="Global navigation"
    >
      <a
        href="./index.html"
        class="is-current"
        aria-current="page"
      >
        Top
      </a>
      <a href="./about.html">
        About
      </a>
      <a href="./service.html">
        Service
      </a>
      <a
        href="./contact.html"
        class="site-nav__cta"
      >
        Contact
      </a>
    </nav>
  </header>

  <main class="site-main">
    <h1>Navigation Sample</h1>
  </main>

  <footer class="site-footer">
    <nav
      class="footer__nav"
      aria-label="Footer navigation"
    >
      <a href="./index.html">
        Top
      </a>
      <a href="./about.html">
        About
      </a>
      <a href="./service.html">
        Service
      </a>
      <a href="./contact.html">
        Contact
      </a>
    </nav>
  </footer>

  <script
    type="module"
    src="./dist/js/core/app.js"
  ></script>
</body>
</html>
"""

        (
            self.project_dir
            / "index.html"
        ).write_text(
            navigation_html,
            encoding="utf-8",
        )

        convert_to_wp.convert_project(
            base_dir=self.base_dir,
            project_name="sample",
            template_name="website",
        )

        header_php = (
            self.project_dir
            / "header.php"
        ).read_text(
            encoding="utf-8"
        )
        footer_php = (
            self.project_dir
            / "footer.php"
        ).read_text(
            encoding="utf-8"
        )

        expected_conditions = (
            "is_front_page()",
            "is_page( 'about' )",
            "is_page( 'service' )",
            "is_page( 'contact' )",
        )

        for condition in (
            expected_conditions
        ):
            with self.subTest(
                condition=condition
            ):
                self.assertIn(
                    condition,
                    header_php,
                )
                self.assertIn(
                    condition,
                    footer_php,
                )

        self.assertEqual(
            4,
            header_php.count(
                'aria-current="page"'
            ),
        )
        self.assertEqual(
            4,
            footer_php.count(
                'aria-current="page"'
            ),
        )

        self.assertNotIn(
            (
                'class="is-current" '
                'aria-current="page">'
            ),
            header_php,
        )
        self.assertNotIn(
            (
                'class="is-current" '
                'aria-current="page">'
            ),
            footer_php,
        )

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

        with warnings.catch_warnings(
            record=True
        ) as caught_warnings:
            warnings.simplefilter("always")

            with self.assertRaises(
                convert_to_wp.ConversionError
            ):
                convert_to_wp.convert_project(
                    base_dir=self.base_dir,
                    project_name="sample",
                    template_name="website",
                )

        self.assertEqual(
            [],
            caught_warnings,
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

    def test_preswap_cleanup_failure_warns_without_masking_conversion_error(
        self,
    ) -> None:
        with (
            patch.object(
                convert_to_wp,
                "generate_wp_stub_files",
                side_effect=(
                    convert_to_wp.ConversionError(
                        "generation failed"
                    )
                ),
            ),
            patch.object(
                convert_to_wp.shutil,
                "rmtree",
                side_effect=OSError(
                    "cleanup failed"
                ),
            ),
            warnings.catch_warnings(
                record=True
            ) as caught_warnings,
        ):
            warnings.simplefilter("always")

            with self.assertRaisesRegex(
                convert_to_wp.ConversionError,
                "generation failed",
            ):
                convert_to_wp.convert_project(
                    base_dir=self.base_dir,
                    project_name="sample",
                    template_name="website",
                )

        warning_messages = [
            str(warning.message)
            for warning in caught_warnings
        ]

        self.assertEqual(
            1,
            len(warning_messages),
        )
        self.assertIn(
            "cleanup failed",
            warning_messages[0],
        )
        self.assertIn(
            ".sample.wp-tmp-",
            warning_messages[0],
        )
        self.assertEqual(
            "keep\n",
            (self.project_dir / "keep.txt").read_text(
                encoding="utf-8"
            ),
        )
        artifacts = (
            convert_to_wp.filesystem_safety
            .find_project_transaction_artifacts(
                self.project_dir
            )
        )
        self.assertEqual(
            1,
            len(artifacts),
        )
        self.assertTrue(
            artifacts[0].name.startswith(
                ".sample.wp-tmp-"
            )
        )

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

    def test_conversion_rejects_unresolved_transaction_artifacts(
        self,
    ) -> None:
        leftover = (
            self.project_dir.parent
            / ".sample.wp-backup-orphan"
        )
        leftover.mkdir()

        with self.assertRaisesRegex(
            RuntimeError,
            "transaction残骸",
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
            )

        self.assertTrue(leftover.exists())

    def test_conversion_rejects_normal_transaction_artifact(
        self,
    ) -> None:
        leftover = (
            self.project_dir.parent
            / ".sample.backup-orphan"
        )
        leftover.mkdir()
        sentinel = leftover / "keep.txt"
        sentinel.write_text(
            "keep\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            str(leftover).replace(
                "\\",
                "\\\\",
            ),
        ):
            convert_to_wp.convert_project(
                base_dir=self.base_dir,
                project_name="sample",
                template_name="website",
            )

        self.assertEqual(
            "keep\n",
            sentinel.read_text(
                encoding="utf-8"
            ),
        )

    def test_swap_and_rollback_failure_preserve_recovery_assets(
        self,
    ) -> None:
        staging_dir = (
            self.project_dir.parent
            / ".sample.wp-tmp-manual"
        )
        staging_dir.mkdir()
        (staging_dir / "replacement.txt").write_text(
            "replacement\n",
            encoding="utf-8",
        )

        def rename_with_failures(
            source: Path,
            destination: Path,
        ) -> Path:
            if (
                source == staging_dir
                and destination == self.project_dir
            ):
                raise OSError("swap failed")

            if (
                source.name.startswith(
                    ".sample.wp-backup-"
                )
                and destination
                == self.project_dir
            ):
                raise OSError("restore failed")

            return source.rename(destination)

        with patch.object(
            convert_to_wp,
            "rename_with_retry",
            side_effect=rename_with_failures,
        ):
            with self.assertRaises(
                convert_to_wp
                .DirectoryTransactionRecoveryError
            ) as context:
                convert_to_wp.replace_directory_transactionally(
                    staging_dir,
                    self.project_dir,
                )

        error = context.exception

        self.assertIsInstance(
            error.__cause__,
            OSError,
        )
        self.assertIn(
            "swap failed",
            str(error.__cause__),
        )
        self.assertIn(
            "restore failed",
            str(error),
        )
        self.assertIn("staging=", str(error))
        self.assertIn("backup=", str(error))
        self.assertIn("failed=", str(error))

        backups = [
            path
            for path
            in self.project_dir.parent.iterdir()
            if path.name.startswith(
                ".sample.wp-backup-"
            )
        ]
        failed = [
            path
            for path
            in self.project_dir.parent.iterdir()
            if path.name.startswith(
                ".sample.wp-failed-"
            )
        ]

        self.assertEqual(1, len(backups))
        self.assertEqual(1, len(failed))
        self.assertFalse(self.project_dir.exists())
        self.assertEqual(
            "keep\n",
            (backups[0] / "keep.txt").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            "replacement\n",
            (
                failed[0]
                / "replacement.txt"
            ).read_text(
                encoding="utf-8"
            ),
        )


if __name__ == "__main__":
    unittest.main()
