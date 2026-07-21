from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from filesystem_safety import (
    assert_no_project_transaction_artifacts,
    find_project_transaction_artifacts,
    is_retryable_windows_rename_error,
    rename_with_retry,
)


def create_windows_error(
    winerror: int,
    message: str,
) -> PermissionError:
    error = PermissionError(message)
    error.winerror = winerror
    return error


class FilesystemSafetyTests(unittest.TestCase):
    def test_project_artifacts_cover_all_operations_without_false_matches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project_dir = (
                root
                / "outputs"
                / "sample"
            )
            project_dir.mkdir(parents=True)

            artifact_paths = [
                project_dir.parent
                / ".sample.failed-z",
                project_dir.parent
                / ".sample.wp-tmp-a",
                project_dir
                / ".dist.backup-c",
                project_dir
                / (
                    ".project-manifest.json"
                    ".failed-b"
                ),
            ]

            for path in artifact_paths:
                path.mkdir()
                (path / "keep.txt").write_text(
                    path.name,
                    encoding="utf-8",
                )

            other_project_paths = [
                project_dir.parent
                / ".sample-other.backup-a",
                project_dir.parent
                / ".samplex.wp-failed-a",
            ]

            for path in other_project_paths:
                path.mkdir()

            expected = tuple(
                sorted(
                    artifact_paths,
                    key=lambda path: (
                        str(path).casefold(),
                        str(path),
                    ),
                )
            )

            self.assertEqual(
                expected,
                find_project_transaction_artifacts(
                    project_dir
                ),
            )

            with self.assertRaises(
                RuntimeError
            ) as context:
                assert_no_project_transaction_artifacts(
                    project_dir
                )

            for path in artifact_paths:
                self.assertIn(
                    str(path),
                    str(context.exception),
                )
                self.assertEqual(
                    path.name,
                    (path / "keep.txt").read_text(
                        encoding="utf-8"
                    ),
                )

            for path in other_project_paths:
                self.assertNotIn(
                    path,
                    expected,
                )

    def test_identifies_retryable_windows_errors(self) -> None:
        for winerror in (5, 32, 33):
            with self.subTest(winerror=winerror):
                error = create_windows_error(
                    winerror,
                    "locked",
                )

                self.assertTrue(
                    is_retryable_windows_rename_error(
                        error
                    )
                )

    def test_retries_transient_access_denied_then_succeeds(
        self,
    ) -> None:
        source = Path("source")
        destination = Path("destination")
        rename_calls: list[
            tuple[Path, Path]
        ] = []

        def flaky_rename(
            path: Path,
            target: Path,
        ) -> Path:
            rename_calls.append(
                (path, target)
            )

            if len(rename_calls) < 3:
                raise create_windows_error(
                    5,
                    "access denied",
                )

            return target

        with (
            patch.object(
                Path,
                "rename",
                new=flaky_rename,
            ),
            patch(
                "filesystem_safety.time.sleep"
            ) as sleep_mock,
        ):
            result = rename_with_retry(
                source,
                destination,
                attempts=4,
                initial_delay_seconds=0.01,
                maximum_delay_seconds=0.02,
            )

        self.assertEqual(
            destination,
            result,
        )
        self.assertEqual(
            3,
            len(rename_calls),
        )
        self.assertEqual(
            [
                call(0.01),
                call(0.02),
            ],
            sleep_mock.call_args_list,
        )

    def test_raises_after_retry_limit(self) -> None:
        source = Path("source")
        destination = Path("destination")
        rename_call_count = 0

        def always_locked(
            path: Path,
            target: Path,
        ) -> Path:
            nonlocal rename_call_count
            rename_call_count += 1

            raise create_windows_error(
                32,
                "sharing violation",
            )

        with (
            patch.object(
                Path,
                "rename",
                new=always_locked,
            ),
            patch(
                "filesystem_safety.time.sleep"
            ) as sleep_mock,
        ):
            with self.assertRaises(
                PermissionError
            ):
                rename_with_retry(
                    source,
                    destination,
                    attempts=3,
                    initial_delay_seconds=0.01,
                    maximum_delay_seconds=0.02,
                )

        self.assertEqual(
            3,
            rename_call_count,
        )
        self.assertEqual(
            [
                call(0.01),
                call(0.02),
            ],
            sleep_mock.call_args_list,
        )

    def test_does_not_retry_non_windows_error(self) -> None:
        source = Path("source")
        destination = Path("destination")
        rename_call_count = 0

        def fail_immediately(
            path: Path,
            target: Path,
        ) -> Path:
            nonlocal rename_call_count
            rename_call_count += 1

            raise OSError(
                "non-retryable failure"
            )

        with (
            patch.object(
                Path,
                "rename",
                new=fail_immediately,
            ),
            patch(
                "filesystem_safety.time.sleep"
            ) as sleep_mock,
        ):
            with self.assertRaisesRegex(
                OSError,
                "non-retryable failure",
            ):
                rename_with_retry(
                    source,
                    destination,
                )

        self.assertEqual(
            1,
            rename_call_count,
        )
        sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
