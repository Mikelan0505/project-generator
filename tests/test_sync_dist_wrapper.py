from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WRAPPER_PATH = REPOSITORY_ROOT / "sync-dist.ps1"
TASKS_PATH = REPOSITORY_ROOT / ".vscode" / "tasks.json"
README_PATH = REPOSITORY_ROOT / "README.md"
AUTO_TASK_LABEL = "Project Generator: Sync dist (auto)"
PROJECT_TASK_LABEL = (
    "Project Generator: Sync dist (project)"
)
POWERSHELL = (
    shutil.which("powershell")
    or shutil.which("pwsh")
)
PYTHON = shutil.which("python")


class SyncDistWrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        if POWERSHELL is None:
            self.skipTest(
                "PowerShell executable is unavailable"
            )

        if PYTHON is None:
            self.skipTest(
                "Python executable is unavailable"
            )

        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.temporary_directory.name
        )
        self.repository = (
            self.root
            / "project-generator"
        )
        self.repository.mkdir()
        self.outputs = (
            self.repository
            / "outputs"
        )
        self.outside_directory = (
            self.root
            / "outside"
        )
        self.outside_directory.mkdir()
        self.log_path = (
            self.root
            / "script-log.json"
        )

        shutil.copy2(
            WRAPPER_PATH,
            self.repository
            / "sync-dist.ps1",
        )
        shutil.copy2(
            REPOSITORY_ROOT
            / "project_naming.py",
            self.repository
            / "project_naming.py",
        )

        (
            self.repository
            / "script.py"
        ).write_text(
            """
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

log_path = os.environ.get("SYNC_DIST_TEST_LOG")

if log_path:
    Path(log_path).write_text(
        json.dumps(
            {
                "argv": sys.argv[1:],
                "cwd": os.getcwd(),
            }
        ),
        encoding="utf-8",
    )

print("stub script output")
raise SystemExit(
    int(
        os.environ.get(
            "SYNC_DIST_TEST_EXIT",
            "0",
        )
    )
)
""".lstrip(),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_wrapper(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_environment = os.environ.copy()
        process_environment[
            "SYNC_DIST_TEST_LOG"
        ] = str(self.log_path)

        if environment:
            process_environment.update(
                environment
            )

        return subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(
                    self.repository
                    / "sync-dist.ps1"
                ),
                *arguments,
            ],
            cwd=self.outside_directory,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=process_environment,
        )

    def read_log(self) -> dict[str, object]:
        return json.loads(
            self.log_path.read_text(
                encoding="utf-8"
            )
        )

    def read_tasks(self) -> dict[str, object]:
        return json.loads(
            TASKS_PATH.read_text(
                encoding="utf-8"
            )
        )

    def get_task(
        self,
        label: str,
    ) -> dict[str, object]:
        tasks = self.read_tasks()["tasks"]
        return next(
            task
            for task in tasks
            if task["label"] == label
        )

    def run_vscode_task(
        self,
        label: str,
        *,
        project: str = "",
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        task = self.get_task(label)
        arguments = [
            argument.replace(
                "${workspaceFolder}",
                str(self.repository),
            ).replace(
                "${input:syncDistProject}",
                project,
            )
            for argument in task["args"]
        ]
        process_environment = os.environ.copy()
        process_environment[
            "SYNC_DIST_TEST_LOG"
        ] = str(self.log_path)

        if environment:
            process_environment.update(
                environment
            )

        return subprocess.run(
            [
                task["command"],
                *arguments,
            ],
            cwd=self.outside_directory,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=process_environment,
        )

    def combined_output(
        self,
        result: subprocess.CompletedProcess[str],
    ) -> str:
        return result.stdout + result.stderr

    def test_wrapper_source_is_thin_and_root_relative(
        self,
    ) -> None:
        self.assertTrue(WRAPPER_PATH.is_file())

        source = WRAPPER_PATH.read_text(
            encoding="utf-8"
        )

        for marker in (
            "$PSScriptRoot",
            "script.py",
            "outputs",
            "--refresh-dist",
            "--project",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

        for prohibited in (
            "Copy-Item",
            "Move-Item",
            "Set-Content",
            "Out-File",
            "Add-Content",
            "convert_to_wp",
            ".html",
            ".php",
        ):
            with self.subTest(
                prohibited=prohibited
            ):
                self.assertNotIn(
                    prohibited,
                    source,
                )

    def test_readme_documents_both_interfaces_and_scope(
        self,
    ) -> None:
        readme = README_PATH.read_text(
            encoding="utf-8"
        )

        for marker in (
            r".\sync-dist.ps1",
            r".\sync-dist.ps1 sample-site",
            (
                "python script.py "
                "--refresh-dist "
                "--project sample-site"
            ),
            "HTMLは変更しない",
            "PHPは変更しない",
            "複数案件",
            "Ctrl+Shift+P",
            "Tasks: Run Task",
            AUTO_TASK_LABEL,
            PROJECT_TASK_LABEL,
            "taskも内部では",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, readme)

    def test_vscode_tasks_delegate_to_wrapper(
        self,
    ) -> None:
        self.assertTrue(TASKS_PATH.is_file())

        document = self.read_tasks()
        self.assertEqual("2.0.0", document["version"])

        tasks = {
            task["label"]: task
            for task in document["tasks"]
        }
        existing_labels = {
            "pg: refresh dist",
            "pg: regenerate website (force)",
            "pg: regenerate shop (force)",
            "pg: regenerate lp (force)",
            "pg: convert website to wp",
            "pg: convert shop to wp",
            "pg: convert lp to wp",
            "pg: website full flow",
            "pg: shop full flow",
            "pg: lp full flow",
        }
        self.assertTrue(
            existing_labels.issubset(tasks)
        )

        auto_task = tasks[AUTO_TASK_LABEL]
        project_task = tasks[PROJECT_TASK_LABEL]
        expected_common_arguments = [
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            r"${workspaceFolder}\sync-dist.ps1",
        ]

        for task in (
            auto_task,
            project_task,
        ):
            with self.subTest(label=task["label"]):
                self.assertEqual(
                    "process",
                    task["type"],
                )
                self.assertEqual(
                    "powershell.exe",
                    task["command"],
                )
                self.assertEqual(
                    expected_common_arguments,
                    task["args"][:5],
                )
                self.assertEqual(
                    [],
                    task["problemMatcher"],
                )

                task_source = json.dumps(task)

                for prohibited in (
                    "Copy-Item",
                    "script.py",
                    "--refresh-dist",
                    "dist/css",
                    "dist/js",
                ):
                    with self.subTest(
                        prohibited=prohibited
                    ):
                        self.assertNotIn(
                            prohibited,
                            task_source,
                        )

        self.assertEqual(
            expected_common_arguments,
            auto_task["args"],
        )
        self.assertNotIn(
            "-Project",
            auto_task["args"],
        )
        self.assertEqual(
            [
                *expected_common_arguments,
                "-Project",
                "${input:syncDistProject}",
            ],
            project_task["args"],
        )

        inputs = {
            item["id"]: item
            for item in document["inputs"]
        }
        self.assertIn("pgProjectName", inputs)
        sync_input = inputs["syncDistProject"]
        self.assertEqual(
            "promptString",
            sync_input["type"],
        )
        self.assertEqual(
            "更新するoutputs内の案件名",
            sync_input["description"],
        )
        self.assertFalse(
            sync_input.get("password", False)
        )

    def test_vscode_tasks_reach_wrapper_outside_repository(
        self,
    ) -> None:
        (
            self.outputs
            / "auto-site"
        ).mkdir(parents=True)

        auto_result = self.run_vscode_task(
            AUTO_TASK_LABEL
        )

        self.assertEqual(
            0,
            auto_result.returncode,
            self.combined_output(auto_result),
        )
        self.assertEqual(
            [
                "--refresh-dist",
                "--project",
                "auto-site",
            ],
            self.read_log()["argv"],
        )

        self.log_path.unlink()
        project_result = self.run_vscode_task(
            PROJECT_TASK_LABEL,
            project="explicit-site",
        )

        self.assertEqual(
            0,
            project_result.returncode,
            self.combined_output(project_result),
        )
        self.assertEqual(
            [
                "--refresh-dist",
                "--project",
                "explicit-site",
            ],
            self.read_log()["argv"],
        )

        failure_result = self.run_vscode_task(
            PROJECT_TASK_LABEL,
            project="failure-site",
            environment={
                "SYNC_DIST_TEST_EXIT": "7",
            },
        )

        self.assertNotEqual(
            0,
            failure_result.returncode,
        )
        self.assertIn(
            "exit code 7",
            self.combined_output(failure_result),
        )

    def test_python_missing_is_rejected(
        self,
    ) -> None:
        empty_path = (
            self.root
            / "empty-path"
        )
        empty_path.mkdir()

        result = self.run_wrapper(
            "sample-site",
            environment={
                "PATH": str(empty_path),
            },
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "was not found in PATH",
            self.combined_output(result),
        )
        self.assertFalse(self.log_path.exists())

    def test_zero_projects_is_rejected(
        self,
    ) -> None:
        self.outputs.mkdir()

        result = self.run_wrapper()

        self.assertNotEqual(0, result.returncode)
        output = self.combined_output(result)
        self.assertIn(
            "No updateable projects",
            output,
        )
        self.assertIn(
            r".\sync-dist.ps1 <project-name>",
            output,
        )
        self.assertFalse(self.log_path.exists())

    def test_one_project_is_auto_selected_outside_repository(
        self,
    ) -> None:
        (
            self.outputs
            / "sample-site"
        ).mkdir(parents=True)

        result = self.run_wrapper()

        self.assertEqual(
            0,
            result.returncode,
            self.combined_output(result),
        )
        self.assertIn(
            "Auto-selected project: sample-site",
            result.stdout,
        )

        log = self.read_log()
        self.assertEqual(
            [
                "--refresh-dist",
                "--project",
                "sample-site",
            ],
            log["argv"],
        )
        self.assertEqual(
            str(self.outside_directory),
            log["cwd"],
        )

    def test_multiple_projects_are_sorted_and_rejected(
        self,
    ) -> None:
        for name in (
            "zeta-site",
            "alpha-site",
        ):
            (
                self.outputs
                / name
            ).mkdir(parents=True)

        result = self.run_wrapper()

        self.assertNotEqual(0, result.returncode)
        output = self.combined_output(result)
        self.assertIn(
            "cannot be auto-selected",
            output,
        )
        self.assertLess(
            output.index("alpha-site"),
            output.index("zeta-site"),
        )
        self.assertIn(
            r".\sync-dist.ps1 <project-name>",
            output,
        )
        self.assertFalse(self.log_path.exists())

    def test_explicit_project_skips_auto_selection(
        self,
    ) -> None:
        result = self.run_wrapper(
            "-Project",
            "explicit-site",
        )

        self.assertEqual(
            0,
            result.returncode,
            self.combined_output(result),
        )
        self.assertEqual(
            [
                "--refresh-dist",
                "--project",
                "explicit-site",
            ],
            self.read_log()["argv"],
        )
        self.assertNotIn(
            "Auto-selected project",
            result.stdout,
        )

    def test_script_failure_is_not_treated_as_success(
        self,
    ) -> None:
        result = self.run_wrapper(
            "sample-site",
            environment={
                "SYNC_DIST_TEST_EXIT": "7",
            },
        )

        self.assertNotEqual(0, result.returncode)
        output = self.combined_output(result)
        self.assertIn(
            "stub script output",
            output,
        )
        self.assertIn(
            "exit code 7",
            output,
        )

    def test_invalid_and_transaction_directories_are_excluded(
        self,
    ) -> None:
        for name in (
            ".sample-site.tmp-test",
            ".hidden",
            "invalid project",
            "valid-site",
        ):
            (
                self.outputs
                / name
            ).mkdir(parents=True)

        result = self.run_wrapper()

        self.assertEqual(
            0,
            result.returncode,
            self.combined_output(result),
        )
        self.assertIn(
            "Auto-selected project: valid-site",
            result.stdout,
        )
        self.assertEqual(
            "valid-site",
            self.read_log()["argv"][-1],
        )


if __name__ == "__main__":
    unittest.main()
