from __future__ import annotations

import time
from pathlib import Path


RETRYABLE_WINDOWS_RENAME_ERRORS = {
    5,
    32,
    33,
}


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
