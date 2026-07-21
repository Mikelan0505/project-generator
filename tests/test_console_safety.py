from __future__ import annotations

import unittest

from console_safety import (
    configure_standard_streams,
    configure_stream_errors,
)


class RecordingStream:
    def __init__(self) -> None:
        self.options: dict = {}

    def reconfigure(
        self,
        **options,
    ) -> None:
        self.options = options


class FailingStream:
    def reconfigure(
        self,
        **options,
    ) -> None:
        raise ValueError(
            "cannot reconfigure"
        )


class ConsoleSafetyTests(unittest.TestCase):
    def test_configures_backslashreplace(
        self,
    ) -> None:
        stream = RecordingStream()

        result = configure_stream_errors(
            stream
        )

        self.assertTrue(result)
        self.assertEqual(
            {
                "errors": (
                    "backslashreplace"
                )
            },
            stream.options,
        )

    def test_unsupported_stream_is_ignored(
        self,
    ) -> None:
        self.assertFalse(
            configure_stream_errors(
                object()
            )
        )

    def test_standard_stream_failures_are_ignored(
        self,
    ) -> None:
        configure_standard_streams(
            stdout=FailingStream(),
            stderr=FailingStream(),
        )


if __name__ == "__main__":
    unittest.main()
