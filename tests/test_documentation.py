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
        self.convert_spec = (
            self.root
            / "convert-to-wp-spec.md"
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
            "npm run check",
            "HTML検証専用の破棄可能な生成物",
            "PROJECT_GENERATOR_PHP",
            "starter-contract.json",
            "requiredCommit",
            "distTreeSha256",
            "requiredAssetSha256",
            "requiredRuntimeTokens",
            "branch非依存",
            "project-manifest.json",
            (
                ".project-generator-"
                "wordpress.json"
            ),
            ".dist.tmp-*",
            ".dist.backup-*",
            ".dist.failed-*",
            ".案件名.failed-*",
            ".案件名.wp-failed-*",
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
            "branch非依存",
            "rollback",
            "所有権",
            "is_front_page()",
            "is_page()",
            "php -l",
            (
                "python -m unittest "
                "discover -s tests -q"
            ),
            "npm run check",
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

        self.assertIn(
            "カスタムフィールド",
            self.handover,
        )
        self.assertNotIn(
            (
                "`functions.php` 連携までは"
                "進めません"
            ),
            self.handover,
        )

    def test_convert_spec_matches_current_capabilities(
        self,
    ) -> None:
        markers = (
            "website",
            "shop",
            "lp",
            "is_front_page()",
            "is_page( '<slug>' )",
            ".project-generator-wordpress.json",
            ".案件名.wp-failed-*",
            "DirectoryTransactionRecoveryError",
        )

        for marker in markers:
            with self.subTest(
                marker=marker
            ):
                self.assertIn(
                    marker,
                    self.convert_spec,
                )

        obsolete_markers = (
            "対象は現時点で `website` と `shop`",
            "current 自動切り替え",
            "`lp` の WordPress 化対応",
        )

        for marker in obsolete_markers:
            with self.subTest(
                obsolete_marker=marker
            ):
                self.assertNotIn(
                    marker,
                    self.convert_spec,
                )

    def test_fail_closed_conversion_contracts_are_documented(
        self,
    ) -> None:
        template_contract_markers = (
            (
                "`project.template`（generation template）と"
                "requested template（`--template`）の一致"
            ),
            "`--force`でもtemplate不一致を許可しない",
            "template migration機能ではなく",
            "staging作成とswapより前",
            "generation manifestを持たない旧案件",
            "静的HTMLや既存案件を変更しない",
        )
        transaction_contract_markers = (
            "操作種別を問わず同じ案件",
            ".案件名.tmp-*",
            ".案件名.wp-failed-*",
            ".dist.tmp-*",
            ".project-manifest.json.failed-*",
            "別案件の残骸は対象外",
            "残骸は自動削除しない",
            (
                "通常生成、`--refresh-dist`、"
                "WordPress変換をすべて停止"
            ),
            "cleanup失敗で残ったstaging",
        )

        documents = (
            (
                "convert spec",
                self.convert_spec,
            ),
            (
                "handover",
                self.handover,
            ),
        )

        for document_name, document in documents:
            for marker in (
                *template_contract_markers,
                *transaction_contract_markers,
            ):
                with self.subTest(
                    document=document_name,
                    marker=marker,
                ):
                    self.assertIn(
                        marker,
                        document,
                    )


if __name__ == "__main__":
    unittest.main()
