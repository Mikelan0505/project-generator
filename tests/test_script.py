from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import script


HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <title>{{PROJECT}} | {{PAGE_TITLE}}</title>
</head>
<body>
  <main>{{DATE}}</main>
</body>
</html>
"""


class GeneratorSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.base_dir = self.root / "project-generator"
        self.base_dir.mkdir()
        self.dist_root = (
            self.root
            / "sass-starter-exiga"
            / "dist"
        )

        self.resolve_dist_patcher = patch.object(
            script,
            "resolve_exiga_dist",
            return_value=self.dist_root,
        )
        self.resolve_dist_patcher.start()

        self.template_dir = self.base_dir / "templates" / "website"
        self.template_dir.mkdir(parents=True)

        (self.template_dir / "index.html").write_text(
            HTML_TEMPLATE,
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.resolve_dist_patcher.stop()
        self.temporary_directory.cleanup()

    def create_dist(self) -> Path:
        dist_root = self.dist_root
        (dist_root / "css").mkdir(parents=True)
        (dist_root / "js" / "core").mkdir(parents=True)

        (dist_root / "css" / "main.css").write_text(
            "/* current css */\n",
            encoding="utf-8",
        )
        (dist_root / "js" / "core" / "app.js").write_text(
            "export {};\n",
            encoding="utf-8",
        )

        return dist_root

    def output_dir(self) -> Path:
        return self.base_dir / "outputs" / "sample"

    def assert_no_transaction_directories(self, parent: Path) -> None:
        leftovers = [
            path.name
            for path in parent.iterdir()
            if path.name.startswith(".sample.tmp-")
            or path.name.startswith(".sample.backup-")
            or path.name.startswith(".sample.failed-")
            or path.name.startswith(".dist.tmp-")
            or path.name.startswith(".dist.backup-")
            or path.name.startswith(".dist.failed-")
            or path.name.startswith(
                ".project-manifest.json.tmp-"
            )
            or path.name.startswith(
                ".project-manifest.json.backup-"
            )
            or path.name.startswith(
                ".project-manifest.json.failed-"
            )
        ]

        self.assertEqual([], leftovers)

    def test_create_rejects_unresolved_transaction_artifacts(
        self,
    ) -> None:
        output_dir = self.output_dir()
        output_dir.parent.mkdir(parents=True)

        leftover = (
            output_dir.parent
            / ".sample.backup-orphan"
        )
        leftover.mkdir()

        with self.assertRaisesRegex(
            RuntimeError,
            "transaction残骸",
        ):
            script.create_project(
                base_dir=self.base_dir,
                template_name="website",
                project_name="sample",
                force=True,
            )

        self.assertTrue(leftover.exists())

    def test_swap_and_rollback_failure_preserve_recovery_assets(
        self,
    ) -> None:
        output_dir = self.output_dir()
        output_dir.mkdir(parents=True)
        (output_dir / "old.txt").write_text(
            "old\n",
            encoding="utf-8",
        )

        staging_dir = (
            output_dir.parent
            / ".sample.tmp-manual"
        )
        staging_dir.mkdir()
        (staging_dir / "new.txt").write_text(
            "new\n",
            encoding="utf-8",
        )

        def rename_with_failures(
            source: Path,
            destination: Path,
        ) -> Path:
            if (
                source == staging_dir
                and destination == output_dir
            ):
                raise OSError("swap failed")

            if (
                source.name.startswith(
                    ".sample.backup-"
                )
                and destination == output_dir
            ):
                raise OSError("restore failed")

            return source.rename(destination)

        with patch.object(
            script,
            "rename_with_retry",
            side_effect=rename_with_failures,
        ):
            with self.assertRaises(
                script.DirectoryTransactionRecoveryError
            ) as context:
                script.replace_directory_transactionally(
                    staging_dir,
                    output_dir,
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
            for path in output_dir.parent.iterdir()
            if path.name.startswith(
                ".sample.backup-"
            )
        ]
        failed = [
            path
            for path in output_dir.parent.iterdir()
            if path.name.startswith(
                ".sample.failed-"
            )
        ]

        self.assertEqual(1, len(backups))
        self.assertEqual(1, len(failed))
        self.assertFalse(output_dir.exists())
        self.assertEqual(
            "old\n",
            (backups[0] / "old.txt").read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            "new\n",
            (failed[0] / "new.txt").read_text(
                encoding="utf-8"
            ),
        )

    def test_force_preflight_failure_preserves_existing_project(self) -> None:
        output_dir = self.output_dir()
        output_dir.mkdir(parents=True)

        sentinel = output_dir / "keep.txt"
        sentinel.write_text("do not delete\n", encoding="utf-8")

        with self.assertRaises(FileNotFoundError):
            script.create_project(
                base_dir=self.base_dir,
                template_name="website",
                project_name="sample",
                force=True,
            )

        self.assertEqual(
            "do not delete\n",
            sentinel.read_text(encoding="utf-8"),
        )
        self.assert_no_transaction_directories(output_dir.parent)

    def test_force_generation_failure_preserves_existing_project(self) -> None:
        self.create_dist()

        output_dir = self.output_dir()
        output_dir.mkdir(parents=True)

        sentinel = output_dir / "keep.txt"
        sentinel.write_text("do not delete\n", encoding="utf-8")

        with patch.object(
            script,
            "copy_exiga_dist",
            side_effect=OSError("copy failed"),
        ):
            with self.assertRaisesRegex(OSError, "copy failed"):
                script.create_project(
                    base_dir=self.base_dir,
                    template_name="website",
                    project_name="sample",
                    force=True,
                )

        self.assertEqual(
            "do not delete\n",
            sentinel.read_text(encoding="utf-8"),
        )
        self.assert_no_transaction_directories(output_dir.parent)

    def test_force_generation_replaces_project_after_success(self) -> None:
        self.create_dist()

        output_dir = self.output_dir()
        output_dir.mkdir(parents=True)
        (output_dir / "old.txt").write_text("old\n", encoding="utf-8")

        result = script.create_project(
            base_dir=self.base_dir,
            template_name="website",
            project_name="sample",
            force=True,
        )

        self.assertEqual(output_dir, result)
        self.assertFalse((output_dir / "old.txt").exists())
        self.assertTrue((output_dir / "index.html").is_file())
        self.assertTrue(
            (output_dir / "dist" / "css" / "main.css").is_file()
        )
        self.assertTrue(
            (output_dir / "dist" / "js" / "core" / "app.js").is_file()
        )
        self.assert_no_transaction_directories(output_dir.parent)

    def test_refresh_dist_mirrors_source_and_removes_stale_files(self) -> None:
        self.create_dist()

        output_dir = self.output_dir()
        stale_css = output_dir / "dist" / "css" / "old.css"
        stale_js = output_dir / "dist" / "js" / "old.js"

        stale_css.parent.mkdir(parents=True)
        stale_js.parent.mkdir(parents=True)
        stale_css.write_text("old\n", encoding="utf-8")
        stale_js.write_text("old\n", encoding="utf-8")

        result = script.refresh_dist(
            base_dir=self.base_dir,
            project_name="sample",
        )

        self.assertEqual(output_dir, result)
        self.assertFalse(stale_css.exists())
        self.assertFalse(stale_js.exists())
        self.assertTrue(
            (output_dir / "dist" / "css" / "main.css").is_file()
        )
        self.assertTrue(
            (output_dir / "dist" / "js" / "core" / "app.js").is_file()
        )
        self.assert_no_transaction_directories(output_dir)

    def test_refresh_copy_failure_preserves_existing_dist(self) -> None:
        self.create_dist()

        output_dir = self.output_dir()
        existing_file = output_dir / "dist" / "css" / "keep.css"
        existing_file.parent.mkdir(parents=True)
        existing_file.write_text("keep\n", encoding="utf-8")

        with patch.object(
            script,
            "copy_exiga_dist",
            side_effect=OSError("copy failed"),
        ):
            with self.assertRaisesRegex(OSError, "copy failed"):
                script.refresh_dist(
                    base_dir=self.base_dir,
                    project_name="sample",
                )

        self.assertEqual(
            "keep\n",
            existing_file.read_text(encoding="utf-8"),
        )
        self.assert_no_transaction_directories(output_dir)

    def test_refresh_preflight_failure_preserves_existing_dist(self) -> None:
        output_dir = self.output_dir()
        existing_file = output_dir / "dist" / "css" / "keep.css"
        existing_file.parent.mkdir(parents=True)
        existing_file.write_text("keep\n", encoding="utf-8")

        with self.assertRaises(FileNotFoundError):
            script.refresh_dist(
                base_dir=self.base_dir,
                project_name="sample",
            )

        self.assertEqual(
            "keep\n",
            existing_file.read_text(encoding="utf-8"),
        )
        self.assert_no_transaction_directories(output_dir)


    def test_refresh_rejects_unresolved_transaction_artifacts(
        self,
    ) -> None:
        output_dir = self.output_dir()
        output_dir.mkdir(
            parents=True
        )

        leftover = (
            output_dir
            / ".dist.backup-orphan"
        )
        leftover.mkdir()

        with self.assertRaisesRegex(
            RuntimeError,
            "transaction残骸",
        ):
            script.refresh_dist(
                base_dir=self.base_dir,
                project_name="sample",
            )

        self.assertTrue(
            leftover.exists()
        )


if __name__ == "__main__":
    unittest.main()
