from __future__ import annotations

import sys
from typing import Any


def configure_stream_errors(
    stream: Any,
) -> bool:
    reconfigure = getattr(
        stream,
        "reconfigure",
        None,
    )

    if not callable(reconfigure):
        return False

    try:
        reconfigure(
            errors="backslashreplace"
        )
    except (
        AttributeError,
        OSError,
        TypeError,
        ValueError,
    ):
        return False

    return True


def configure_standard_streams(
    *,
    stdout: Any | None = None,
    stderr: Any | None = None,
) -> None:
    active_stdout = (
        sys.stdout
        if stdout is None
        else stdout
    )
    active_stderr = (
        sys.stderr
        if stderr is None
        else stderr
    )

    configure_stream_errors(
        active_stdout
    )
    configure_stream_errors(
        active_stderr
    )
