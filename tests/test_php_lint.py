from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import convert_to_wp


def find_php_executable() -> Path | None:
    candidates: list[Path] = []

    configured = os.environ.get(
        "PROJECT_GENERATOR_PHP"
    )

    if configured:
        candidates.append(
            Path(configured)
        )

    command = shutil.which("php")

    if command:
        candidates.append(
            Path(command)
        )

    search_roots = []

    appdata = os.environ.get(
        "APPDATA"
    )
    local_appdata = os.environ.get(
        "LOCALAPPDATA"
    )

    if appdata:
        search_roots.append(
            Path(appdata)
            / "Local"
            / "lightning-services"
        )

    if local_appdata:
        search_roots.append(
            Path(local_appdata)
            / "Programs"
            / "Local"
            / "resources"
            / "extraResources"
            / "lightning-services"
        )

    for search_root in search_roots:
        if not search_root.is_dir():
            continue

        candidates.extend(
            sorted(
                search_root.glob(
                    "php-*/bin/win64/php.exe"
                ),
                reverse=True,
            )
        )
        candidates.extend(
            sorted(
                search_root.glob(
                    "php-*/bin/win32/php.exe"
                ),
                reverse=True,
            )
        )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    return None


class GeneratedPhpLintTests(
    unittest.TestCase
):
    def test_generated_php_passes_php_lint(
        self,
    ) -> None:
        php_executable = (
            find_php_executable()
        )

        if php_executable is None:
            self.skipTest(
                "PHP executable is unavailable"
            )

        repository_root = (
            Path(__file__).resolve()
            .parents[1]
        )

        with tempfile.TemporaryDirectory() as temp:
            base_dir = (
                Path(temp)
                / "project-generator"
            )
            outputs_dir = (
                base_dir
                / "outputs"
            )
            outputs_dir.mkdir(
                parents=True
            )

            shutil.copytree(
                repository_root
                / "wp-stubs",
                base_dir
                / "wp-stubs",
            )

            for template_name in (
                "website",
                "shop",
                "lp",
            ):
                with self.subTest(
                    template=template_name
                ):
                    project_name = (
                        f"php-lint-{template_name}"
                    )
                    project_dir = (
                        outputs_dir
                        / project_name
                    )

                    shutil.copytree(
                        repository_root
                        / "templates"
                        / template_name,
                        project_dir,
                    )

                    (
                        project_dir
                        / "project-manifest.json"
                    ).write_text(
                        json.dumps(
                            {
                                "schemaVersion": 1,
                                "project": {
                                    "template": (
                                        template_name
                                    ),
                                },
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )

                    (
                        converted_dir,
                        generated_files,
                    ) = (
                        convert_to_wp
                        .convert_project(
                            base_dir=base_dir,
                            project_name=(
                                project_name
                            ),
                            template_name=(
                                template_name
                            ),
                        )
                    )

                    ownership_path = (
                        converted_dir
                        / (
                            convert_to_wp
                            .WP_OWNERSHIP_MANIFEST_FILENAME
                        )
                    )

                    ownership = json.loads(
                        ownership_path.read_text(
                            encoding="utf-8"
                        )
                    )

                    owned_paths = {
                        record["path"]
                        for record
                        in ownership[
                            "generatedFiles"
                        ]
                    }

                    self.assertEqual(
                        set(generated_files),
                        owned_paths,
                    )

                    php_files = [
                        converted_dir / name
                        for name in generated_files
                        if name.endswith(".php")
                    ]

                    self.assertTrue(
                        php_files
                    )

                    for php_file in php_files:
                        result = subprocess.run(
                            [
                                str(
                                    php_executable
                                ),
                                "-l",
                                str(php_file),
                            ],
                            check=False,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                        )

                        self.assertEqual(
                            0,
                            result.returncode,
                            msg=(
                                f"{php_file}\n"
                                f"{result.stdout}\n"
                                f"{result.stderr}"
                            ),
                        )


if __name__ == "__main__":
    unittest.main()
