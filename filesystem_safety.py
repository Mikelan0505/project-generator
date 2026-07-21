from __future__ import annotations

import shutil
import time
import warnings
from pathlib import Path
from typing import Callable
from uuid import uuid4


RETRYABLE_WINDOWS_RENAME_ERRORS = {
    5,
    32,
    33,
}


class DirectoryTransactionRecoveryError(RuntimeError):
    def __init__(
        self,
        *,
        original_error: Exception,
        recovery_errors: list[
            tuple[str, Exception]
        ],
        staging_dir: Path,
        backup_dir: Path,
        failed_dir: Path,
    ) -> None:
        self.original_error = original_error
        self.recovery_errors = tuple(
            recovery_errors
        )
        self.staging_dir = staging_dir
        self.backup_dir = backup_dir
        self.failed_dir = failed_dir

        recovery_detail = "; ".join(
            (
                f"{label}: "
                f"{type(error).__name__}: "
                f"{error}"
            )
            for label, error
            in recovery_errors
        )

        super().__init__(
            "directory transactionに失敗し、"
            "rollbackも完了しませんでした。"
            f" original="
            f"{type(original_error).__name__}: "
            f"{original_error};"
            f" recovery={recovery_detail};"
            f" staging={staging_dir};"
            f" backup={backup_dir};"
            f" failed={failed_dir}"
        )


def is_retryable_windows_rename_error(
    error: OSError,
) -> bool:
    return (
        getattr(error, "winerror", None)
        in RETRYABLE_WINDOWS_RENAME_ERRORS
    )


def rename_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int = 10,
    initial_delay_seconds: float = 0.05,
    maximum_delay_seconds: float = 0.5,
) -> Path:
    if attempts < 1:
        raise ValueError(
            "attemptsは1以上である必要があります。"
        )

    if initial_delay_seconds < 0:
        raise ValueError(
            "initial_delay_secondsは0以上である必要があります。"
        )

    if maximum_delay_seconds < 0:
        raise ValueError(
            "maximum_delay_secondsは0以上である必要があります。"
        )

    for attempt_index in range(attempts):
        try:
            return source.rename(destination)
        except OSError as error:
            is_last_attempt = (
                attempt_index == attempts - 1
            )

            if (
                is_last_attempt
                or not is_retryable_windows_rename_error(error)
            ):
                raise

            delay_seconds = min(
                initial_delay_seconds * (2 ** attempt_index),
                maximum_delay_seconds,
            )

            time.sleep(delay_seconds)

    raise AssertionError(
        "到達不能なrename再試行状態です。"
    )


def directory_transaction_prefixes(
    destination_dir: Path,
    *,
    transaction_label: str = "",
) -> tuple[str, str, str]:
    label_prefix = (
        f"{transaction_label}-"
        if transaction_label
        else ""
    )
    artifact_base = (
        f".{destination_dir.name}."
        f"{label_prefix}"
    )

    return (
        f"{artifact_base}tmp-",
        f"{artifact_base}backup-",
        f"{artifact_base}failed-",
    )


def find_directory_transaction_artifacts(
    destination_dir: Path,
    *,
    transaction_label: str = "",
) -> tuple[Path, ...]:
    parent_dir = destination_dir.parent

    if not parent_dir.is_dir():
        return ()

    prefixes = directory_transaction_prefixes(
        destination_dir,
        transaction_label=transaction_label,
    )

    return tuple(
        sorted(
            (
                path
                for path in parent_dir.iterdir()
                if any(
                    path.name.startswith(prefix)
                    for prefix in prefixes
                )
            ),
            key=lambda path: path.name,
        )
    )


def assert_no_directory_transaction_artifacts(
    destination_dir: Path,
    *,
    transaction_label: str = "",
) -> None:
    artifacts = find_directory_transaction_artifacts(
        destination_dir,
        transaction_label=transaction_label,
    )

    if not artifacts:
        return

    detail = "\n".join(
        f"- {path}"
        for path in artifacts
    )

    raise RuntimeError(
        "前回のdirectory transaction残骸が"
        "見つかりました。"
        "自動処理を停止します。"
        "内容を確認してから復旧または削除"
        "してください。\n"
        f"{detail}"
    )


def remove_path_quietly(
    path: Path,
) -> None:
    try:
        if not path.exists():
            return

        if path.is_dir():
            shutil.rmtree(path)
            return

        path.unlink()
    except OSError as error:
        warnings.warn(
            "directory transaction cleanupに"
            "失敗しました。"
            f" path={path}"
            f" error={type(error).__name__}: "
            f"{error}",
            RuntimeWarning,
            stacklevel=2,
        )


def replace_directory_transactionally(
    staging_dir: Path,
    destination_dir: Path,
    *,
    transaction_label: str = "",
    rename_path: (
        Callable[[Path, Path], Path]
        | None
    ) = None,
) -> None:
    if not staging_dir.is_dir():
        raise FileNotFoundError(
            "置換元stagingがディレクトリでは"
            f"ありません: {staging_dir}"
        )

    if (
        destination_dir.exists()
        and not destination_dir.is_dir()
    ):
        raise FileExistsError(
            "置換対象がディレクトリでは"
            f"ありません: {destination_dir}"
        )

    rename_operation = (
        rename_path
        if rename_path is not None
        else rename_with_retry
    )
    transaction_id = uuid4().hex
    label_prefix = (
        f"{transaction_label}-"
        if transaction_label
        else ""
    )
    artifact_base = (
        f".{destination_dir.name}."
        f"{label_prefix}"
    )
    backup_dir = destination_dir.parent / (
        f"{artifact_base}backup-"
        f"{transaction_id}"
    )
    failed_dir = destination_dir.parent / (
        f"{artifact_base}failed-"
        f"{transaction_id}"
    )
    had_destination = destination_dir.exists()

    try:
        if had_destination:
            rename_operation(
                destination_dir,
                backup_dir,
            )

        rename_operation(
            staging_dir,
            destination_dir,
        )
    except Exception as original_error:
        recovery_errors: list[
            tuple[str, Exception]
        ] = []

        def attempt_recovery_rename(
            *,
            label: str,
            source: Path,
            destination: Path,
        ) -> bool:
            try:
                rename_operation(
                    source,
                    destination,
                )
            except Exception as error:
                recovery_errors.append(
                    (label, error)
                )
                return False

            return True

        if staging_dir.exists():
            attempt_recovery_rename(
                label=(
                    "new directory quarantine"
                ),
                source=staging_dir,
                destination=failed_dir,
            )
        elif destination_dir.exists():
            attempt_recovery_rename(
                label=(
                    "new directory quarantine"
                ),
                source=destination_dir,
                destination=failed_dir,
            )

        if backup_dir.exists():
            if destination_dir.exists():
                recovery_errors.append(
                    (
                        "old directory restore",
                        RuntimeError(
                            "復元先directoryが"
                            "使用中です: "
                            f"{destination_dir}"
                        ),
                    )
                )
            else:
                attempt_recovery_rename(
                    label=(
                        "old directory restore"
                    ),
                    source=backup_dir,
                    destination=destination_dir,
                )

        if recovery_errors:
            raise DirectoryTransactionRecoveryError(
                original_error=original_error,
                recovery_errors=recovery_errors,
                staging_dir=staging_dir,
                backup_dir=backup_dir,
                failed_dir=failed_dir,
            ) from original_error

        remove_path_quietly(failed_dir)
        raise
    else:
        remove_path_quietly(backup_dir)
