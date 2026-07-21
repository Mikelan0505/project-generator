from __future__ import annotations

import unittest
from pathlib import Path


class DocumentationSafetyTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve()
            .parents[1]
        )
        self.readme = (
            self.root
            / "README.md"
        ).read_text(
            encoding="utf-8"
        )
        self.handover = (
            self.root
            / "docs"
            / "project-generator-handover.md"
        ).read_text(
            encoding="utf-8"
        )

    def test_readme_documents_current_safety_contract(
        self,
    ) -> None:
        markers = (
            (
                "python -m unittest "
                "discover -s tests -q"
            ),
            "PROJECT_GENERATOR_PHP",
            "starter-contract.json",
            "requiredCommit",
            "distTreeSha256",
            "requiredAssetSha256",
            "requiredRuntimeTokens",
            "project-manifest.json",
            (
                ".project-generator-"
                "wordpress.json"
            ),
            ".dist.tmp-*",
            ".dist.backup-*",
            ".dist.failed-*",
            'aria-current="page"',
        )

        for marker in markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.readme,
                )

    def test_handover_documents_current_safety_contract(
        self,
    ) -> None:
        markers = (
            "静的文字列リテラル",
            "traversal",
            "rollback",
            "所有権",
            "is_front_page()",
            "is_page()",
            "php -l",
            (
                "python -m unittest "
                "discover -s tests -q"
            ),
            "git diff --check",
        )

        for marker in markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.handover,
                )


if __name__ == "__main__":
    unittest.main()
