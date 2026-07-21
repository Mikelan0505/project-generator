from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import script
from generation_manifest import (
    MANIFEST_FILENAME,
    hash_directory_tree,
    sha256_file,
)


HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <title>{{PROJECT}} | {{PAGE_TITLE}}</title>
</head>
<body>
  <main>{{PROJECT}} / {{DATE}}</main>
</body>
</html>
"""


class GenerationManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.temporary_directory.name
        )
        self.base_dir = (
            self.root
            / "project-generator"
        )
        self.template_dir = (
            self.base_dir
            / "templates"
            / "lp"
        )
        self.template_dir.mkdir(parents=True)

        (
            self.template_dir
            / "index.html"
        ).write_text(
            HTML_TEMPLATE,
            encoding="utf-8",
        )

        self.starter_root = (
            self.root
            / "sass-starter-exiga"
        )
        self.dist_root = (
            self.starter_root
            / "dist"
        )

        (
            self.dist_root
            / "css"
        ).mkdir(parents=True)
        (
            self.dist_root
            / "js"
            / "core"
        ).mkdir(parents=True)

        (
            self.dist_root
            / "css"
            / "main.css"
        ).write_text(
            "/* initial css */\n",
            encoding="utf-8",
        )

        (
            self.dist_root
            / "js"
            / "core"
            / "app.js"
        ).write_text(
            "export {};\n",
            encoding="utf-8",
        )

        self.resolve_dist_patcher = patch.object(
            script,
            "resolve_exiga_dist",
            return_value=self.dist_root,
        )
        self.resolve_dist_patcher.start()

    def tearDown(self) -> None:
        self.resolve_dist_patcher.stop()
        self.temporary_directory.cleanup()

    def read_manifest(
        self,
        output_dir: Path,
    ) -> dict:
        return json.loads(
            (
                output_dir
                / MANIFEST_FILENAME
            ).read_text(encoding="utf-8")
        )

    def test_create_project_writes_traceable_manifest(
        self,
    ) -> None:
        output_dir = script.create_project(
            base_dir=self.base_dir,
            template_name="lp",
            project_name="Manifest Sample",
            force=True,
        )

        manifest = self.read_manifest(
            output_dir
        )

        self.assertEqual(
            1,
            manifest["schemaVersion"],
        )
        self.assertEqual(
            "Manifest Sample",
            manifest["project"]["name"],
        )
        self.assertEqual(
            "Manifest-Sample",
            manifest["project"]["slug"],
        )
        self.assertEqual(
            "lp",
            manifest["project"]["template"],
        )
        self.assertEqual(
            "create",
            manifest["operation"],
        )

        asset_records = {
            record["path"]: record["sha256"]
            for record in (
                manifest["dist"]["requiredAssets"]
            )
        }

        self.assertEqual(
            sha256_file(
                output_dir
                / "dist"
                / "css"
                / "main.css"
            ),
            asset_records[
                "dist/css/main.css"
            ],
        )
        self.assertEqual(
            sha256_file(
                output_dir
                / "dist"
                / "js"
                / "core"
                / "app.js"
            ),
            asset_records[
                "dist/js/core/app.js"
            ],
        )
        self.assertEqual(
            2,
            manifest["dist"]["tree"]["fileCount"],
        )

    def test_refresh_updates_manifest_and_asset_hash(
        self,
    ) -> None:
        output_dir = script.create_project(
            base_dir=self.base_dir,
            template_name="lp",
            project_name="Refresh Sample",
            force=True,
        )

        initial_manifest = self.read_manifest(
            output_dir
        )
        initial_css_hash = {
            record["path"]: record["sha256"]
            for record in (
                initial_manifest[
                    "dist"
                ]["requiredAssets"]
            )
        }["dist/css/main.css"]

        (
            self.dist_root
            / "css"
            / "main.css"
        ).write_text(
            "/* refreshed css */\n",
            encoding="utf-8",
        )

        script.refresh_dist(
            base_dir=self.base_dir,
            project_name="Refresh-Sample",
        )

        refreshed_manifest = self.read_manifest(
            output_dir
        )
        refreshed_css_hash = {
            record["path"]: record["sha256"]
            for record in (
                refreshed_manifest[
                    "dist"
                ]["requiredAssets"]
            )
        }["dist/css/main.css"]

        self.assertEqual(
            "refresh-dist",
            refreshed_manifest["operation"],
        )
        self.assertEqual(
            initial_manifest["createdAt"],
            refreshed_manifest["createdAt"],
        )
        self.assertEqual(
            "lp",
            refreshed_manifest[
                "project"
            ]["template"],
        )
        self.assertEqual(
            "Refresh Sample",
            refreshed_manifest[
                "project"
            ]["name"],
        )
        self.assertNotEqual(
            initial_css_hash,
            refreshed_css_hash,
        )
        self.assertEqual(
            sha256_file(
                output_dir
                / "dist"
                / "css"
                / "main.css"
            ),
            refreshed_css_hash,
        )

    def test_each_forward_rename_failure_restores_old_assets(
        self,
    ) -> None:
        for failure_call in range(1, 5):
            with self.subTest(
                failure_call=failure_call
            ):
                output_dir = (
                    self.base_dir
                    / "outputs"
                    / f"sample-{failure_call}"
                )
                destination_dist = (
                    output_dir
                    / "dist"
                )
                destination_dist.mkdir(
                    parents=True
                )

                (
                    destination_dist
                    / "old.txt"
                ).write_text(
                    "old dist\n",
                    encoding="utf-8",
                )

                destination_manifest = (
                    output_dir
                    / MANIFEST_FILENAME
                )
                destination_manifest.write_text(
                    "old manifest\n",
                    encoding="utf-8",
                )

                staging_dist = (
                    output_dir
                    / ".dist.tmp-test"
                )
                staging_dist.mkdir()

                (
                    staging_dist
                    / "new.txt"
                ).write_text(
                    "new dist\n",
                    encoding="utf-8",
                )

                staging_manifest = (
                    output_dir
                    / (
                        ".project-manifest.json"
                        ".tmp-test"
                    )
                )
                staging_manifest.write_text(
                    "new manifest\n",
                    encoding="utf-8",
                )

                call_count = 0

                def rename_with_failure(
                    source: Path,
                    destination: Path,
                ) -> Path:
                    nonlocal call_count
                    call_count += 1

                    if (
                        call_count
                        == failure_call
                    ):
                        raise OSError(
                            "forward rename failed "
                            f"at {failure_call}"
                        )

                    return source.rename(
                        destination
                    )

                with patch.object(
                    script,
                    "rename_with_retry",
                    side_effect=(
                        rename_with_failure
                    ),
                ):
                    with self.assertRaisesRegex(
                        OSError,
                        (
                            "forward rename failed "
                            f"at {failure_call}"
                        ),
                    ):
                        script.replace_dist_and_manifest_transactionally(
                            staging_dist_dir=(
                                staging_dist
                            ),
                            staging_manifest_path=(
                                staging_manifest
                            ),
                            output_dir=output_dir,
                        )

                self.assertEqual(
                    "old dist\n",
                    (
                        destination_dist
                        / "old.txt"
                    ).read_text(
                        encoding="utf-8"
                    ),
                )
                self.assertEqual(
                    "old manifest\n",
                    destination_manifest.read_text(
                        encoding="utf-8"
                    ),
                )

                leftovers = [
                    path.name
                    for path
                    in output_dir.iterdir()
                    if (
                        ".backup-"
                        in path.name
                        or ".failed-"
                        in path.name
                    )
                ]

                self.assertEqual(
                    [],
                    leftovers,
                )

    def test_rollback_failure_preserves_recovery_assets_and_original_error(
        self,
    ) -> None:
        output_dir = (
            self.base_dir
            / "outputs"
            / "rollback-failure"
        )
        destination_dist = (
            output_dir
            / "dist"
        )
        destination_dist.mkdir(
            parents=True
        )

        (
            destination_dist
            / "old.txt"
        ).write_text(
            "old dist\n",
            encoding="utf-8",
        )

        destination_manifest = (
            output_dir
            / MANIFEST_FILENAME
        )
        destination_manifest.write_text(
            "old manifest\n",
            encoding="utf-8",
        )

        staging_dist = (
            output_dir
            / ".dist.tmp-test"
        )
        staging_dist.mkdir()

        (
            staging_dist
            / "new.txt"
        ).write_text(
            "new dist\n",
            encoding="utf-8",
        )

        staging_manifest = (
            output_dir
            / (
                ".project-manifest.json"
                ".tmp-test"
            )
        )
        staging_manifest.write_text(
            "new manifest\n",
            encoding="utf-8",
        )

        call_count = 0

        def rename_with_failures(
            source: Path,
            destination: Path,
        ) -> Path:
            nonlocal call_count
            call_count += 1

            if call_count == 4:
                raise OSError(
                    "manifest swap failed"
                )

            if (
                source.name.startswith(
                    ".dist.backup-"
                )
                and destination
                == destination_dist
            ):
                raise OSError(
                    "dist restore failed"
                )

            return source.rename(
                destination
            )

        with patch.object(
            script,
            "rename_with_retry",
            side_effect=(
                rename_with_failures
            ),
        ):
            with self.assertRaises(
                script.DistRefreshRecoveryError
            ) as context:
                script.replace_dist_and_manifest_transactionally(
                    staging_dist_dir=(
                        staging_dist
                    ),
                    staging_manifest_path=(
                        staging_manifest
                    ),
                    output_dir=output_dir,
                )

        error = context.exception

        self.assertIsInstance(
            error.__cause__,
            OSError,
        )
        self.assertIn(
            "manifest swap failed",
            str(error.__cause__),
        )
        self.assertIn(
            "dist restore failed",
            str(error),
        )
        self.assertIn(
            "backup_dist=",
            str(error),
        )
        self.assertIn(
            "failed_dist=",
            str(error),
        )

        backup_dist = [
            path
            for path
            in output_dir.iterdir()
            if path.name.startswith(
                ".dist.backup-"
            )
        ]
        failed_dist = [
            path
            for path
            in output_dir.iterdir()
            if path.name.startswith(
                ".dist.failed-"
            )
        ]

        self.assertEqual(
            1,
            len(backup_dist),
        )
        self.assertEqual(
            1,
            len(failed_dist),
        )
        self.assertEqual(
            "old dist\n",
            (
                backup_dist[0]
                / "old.txt"
            ).read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            "new dist\n",
            (
                failed_dist[0]
                / "new.txt"
            ).read_text(
                encoding="utf-8"
            ),
        )
        self.assertEqual(
            "old manifest\n",
            destination_manifest.read_text(
                encoding="utf-8"
            ),
        )

    def test_cleanup_failure_emits_warning(
        self,
    ) -> None:
        cleanup_dir = (
            self.root
            / "cleanup-failure"
        )
        cleanup_dir.mkdir()

        with patch.object(
            script.shutil,
            "rmtree",
            side_effect=OSError(
                "cleanup failed"
            ),
        ):
            with self.assertWarnsRegex(
                RuntimeWarning,
                "cleanup failed",
            ):
                script.remove_path_quietly(
                    cleanup_dir
                )

        self.assertTrue(
            cleanup_dir.exists()
        )

    def test_tree_hash_changes_when_content_changes(
        self,
    ) -> None:
        directory = self.root / "hash-tree"
        directory.mkdir()

        file_path = directory / "sample.txt"
        file_path.write_text(
            "before\n",
            encoding="utf-8",
        )

        before = hash_directory_tree(
            directory
        )

        file_path.write_text(
            "after\n",
            encoding="utf-8",
        )

        after = hash_directory_tree(
            directory
        )

        self.assertNotEqual(
            before["sha256"],
            after["sha256"],
        )


if __name__ == "__main__":
    unittest.main()
