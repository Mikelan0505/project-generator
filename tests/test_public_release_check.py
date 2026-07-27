from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import script
from tools import public_release_check


BASE_URL = "https://www.client.test/site/"


class PublicReleaseFixture:
    def __init__(
        self,
        root: Path,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        self.root = root
        self.base_url = base_url
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def public_url(
        self,
        relative_path: str,
    ) -> str:
        return (
            f"{self.base_url}"
            f"{relative_path}"
        )

    def html(
        self,
        *,
        relative_path: str = "index.html",
        head: str = "",
        body: str = "",
    ) -> Path:
        canonical = self.public_url(
            relative_path
        )
        content = f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>公開案件</title>
    <meta name="description" content="公開案件の説明です。" />
    <link rel="canonical" href="{canonical}" />
    <meta property="og:title" content="公開案件" />
    <meta property="og:description" content="公開案件の説明です。" />
    <meta property="og:url" content="{canonical}" />
    <meta property="og:image" content="https://cdn.client.test/og.webp" />
{head}
  </head>
  <body>
    <main>
      <h1 id="top">公開案件</h1>
{body}
    </main>
  </body>
</html>
"""
        path = self.root / relative_path
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            content,
            encoding="utf-8",
        )
        return path


def no_html_violations(
    _root: Path,
    _paths,
) -> tuple[()]:
    return ()


class PublicReleaseCheckTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory(
                prefix="公開 前検査 ",
            )
        )
        self.temporary_root = Path(
            self.temporary_directory.name
        )
        self.root = (
            self.temporary_root
            / "日本語 案件"
        )
        self.fixture = (
            PublicReleaseFixture(
                self.root
            )
        )
        self.base_url = (
            public_release_check
            .normalize_base_url(
                BASE_URL
            )
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def inspect(
        self,
    ) -> tuple[
        int,
        list[
            public_release_check.Finding
        ],
    ]:
        return (
            public_release_check
            .inspect_public_root(
                root=self.root.resolve(),
                base_url=self.base_url,
                html_validator=(
                    no_html_violations
                ),
            )
        )

    def rule_ids(
        self,
    ) -> list[str]:
        return [
            finding.rule_id
            for finding in self.inspect()[1]
        ]

    def test_complete_minimal_html_passes(
        self,
    ) -> None:
        self.fixture.html()

        html_count, findings = (
            self.inspect()
        )

        self.assertEqual(1, html_count)
        self.assertEqual([], findings)

    def test_relative_root_and_base_without_trailing_slash(
        self,
    ) -> None:
        relative_root = os.path.relpath(
            self.root,
            Path.cwd(),
        )

        self.assertEqual(
            self.root.resolve(),
            public_release_check.resolve_root(
                relative_root
            ),
        )
        self.assertEqual(
            "/site/",
            (
                public_release_check
                .normalize_base_url(
                    "https://www.client.test/site"
                )
                .path_prefix
            ),
        )

    def test_complete_minimal_html_passes_with_local_html_validate(
        self,
    ) -> None:
        self.fixture.html()

        html_count, findings = (
            public_release_check
            .inspect_public_root(
                root=self.root.resolve(),
                base_url=self.base_url,
            )
        )

        self.assertEqual(1, html_count)
        self.assertEqual([], findings)

    def create_generated_template(
        self,
        template_name: str,
    ) -> Path:
        repository_root = (
            Path(__file__).resolve()
            .parents[1]
        )
        generated_root = (
            self.temporary_root
            / f"generated-{template_name}"
        )
        shutil.copytree(
            (
                repository_root
                / "templates"
                / template_name
            ),
            generated_root,
        )
        script.prepare_html_files(
            generated_root,
            template_name=template_name,
            project_name="未編集案件",
            generated_date="2026-07-27",
        )
        return generated_root

    def assert_generated_template_fails(
        self,
        template_name: str,
    ) -> None:
        generated_root = (
            self.create_generated_template(
                template_name
            )
        )
        html_count, findings = (
            public_release_check
            .inspect_public_root(
                root=generated_root,
                base_url=self.base_url,
                html_validator=(
                    no_html_violations
                ),
            )
        )

        self.assertGreater(
            html_count,
            0,
        )
        self.assertTrue(findings)
        self.assertIn(
            "DUMMY_GENERATOR_CREDIT",
            {
                finding.rule_id
                for finding in findings
            },
        )

    def test_unedited_website_generation_fails(
        self,
    ) -> None:
        self.assert_generated_template_fails(
            "website"
        )

    def test_unedited_lp_generation_fails(
        self,
    ) -> None:
        self.assert_generated_template_fails(
            "lp"
        )

    def test_unedited_shop_generation_fails(
        self,
    ) -> None:
        self.assert_generated_template_fails(
            "shop"
        )

    def test_dummy_markers_are_detected(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                "      <p>{{CLIENT}}</p>\n"
                "      <p>20XX年 〇〇区</p>\n"
                "      <p>example.com</p>\n"
                "      <p>info@example.com</p>\n"
                "      <p>差し替えメモ</p>\n"
                "      <p>Generated from "
                "project-generator</p>\n"
                "      <p>仕事用スターターとして"
                "最初の構成を整えた状態です。"
                "必要な情報へ差し替えて利用します。"
                "</p>"
            )
        )

        rules = set(
            self.rule_ids()
        )

        self.assertTrue(
            {
                "DUMMY_PLACEHOLDER",
                "DUMMY_YEAR",
                "DUMMY_CIRCLE",
                "DUMMY_EXAMPLE_DOMAIN",
                "DUMMY_EXAMPLE_EMAIL",
                "DUMMY_REPLACEMENT_NOTE",
                "DUMMY_GENERATOR_CREDIT",
                "DUMMY_STARTER_COPY",
            }.issubset(rules)
        )

    def test_form_action_hash_is_detected(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '      <form action="#" '
                'method="post"></form>'
            )
        )

        self.assertIn(
            "FORM_ACTION_INVALID",
            self.rule_ids(),
        )

    def test_form_without_action_is_detected(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '      <form method="post">'
                "</form>"
            )
        )

        self.assertIn(
            "FORM_ACTION_MISSING",
            self.rule_ids(),
        )

    def test_existing_relative_and_https_form_actions_pass(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '      <form action="./send.php" '
                'method="post"></form>\n'
                "      <form "
                'action="https://forms.client.test/'
                'submit" method="post"></form>'
            )
        )
        (
            self.root
            / "send.php"
        ).write_text(
            "<?php\n",
            encoding="utf-8",
        )

        rules = self.rule_ids()

        self.assertNotIn(
            "FORM_ACTION_INVALID",
            rules,
        )
        self.assertNotIn(
            "INTERNAL_REFERENCE_MISSING",
            rules,
        )

    def test_development_urls_are_detected_in_public_text(
        self,
    ) -> None:
        self.fixture.html()
        (
            self.root
            / "app.js"
        ).write_text(
            (
                'const urls = ["http://localhost:3000", '
                '"http://127.0.0.1", "http://0.0.0.0", '
                '"http://[::1]", "file:///tmp/x"];\n'
            ),
            encoding="utf-8",
        )

        matching = [
            finding
            for finding in self.inspect()[1]
            if (
                finding.rule_id
                == "DEVELOPMENT_URL"
            )
        ]

        self.assertEqual(
            1,
            len(matching),
        )

    def test_htaccess_and_tabular_text_are_scanned(
        self,
    ) -> None:
        self.fixture.html()
        (
            self.root
            / ".htaccess"
        ).write_text(
            (
                "RewriteRule ^api$ "
                "http://localhost:3000 [P]\n"
            ),
            encoding="utf-8",
        )
        (
            self.root
            / "contacts.csv"
        ).write_text(
            "name,url\nsample,https://example.com\n",
            encoding="utf-8",
        )

        findings = self.inspect()[1]

        self.assertTrue(
            any(
                finding.relative_path
                == ".htaccess"
                and finding.rule_id
                == "DEVELOPMENT_URL"
                for finding in findings
            )
        )
        self.assertTrue(
            any(
                finding.relative_path
                == "contacts.csv"
                and finding.rule_id
                == "DUMMY_EXAMPLE_DOMAIN"
                for finding in findings
            )
        )

    def test_title_and_description_contracts(
        self,
    ) -> None:
        path = self.fixture.html()
        content = path.read_text(
            encoding="utf-8"
        )
        content = content.replace(
            "    <title>公開案件</title>\n",
            "",
        ).replace(
            (
                '    <meta name="description" '
                'content="公開案件の説明です。" />\n'
            ),
            "",
        )
        path.write_text(
            content,
            encoding="utf-8",
        )

        rules = self.rule_ids()

        self.assertIn(
            "SEO_TITLE_COUNT",
            rules,
        )
        self.assertIn(
            "SEO_DESCRIPTION_COUNT",
            rules,
        )

    def test_canonical_contracts(
        self,
    ) -> None:
        cases = (
            (
                "",
                "SEO_CANONICAL_COUNT",
            ),
            (
                (
                    '    <link rel="canonical" '
                    'href="http://www.client.test/'
                    'site/index.html" />\n'
                ),
                "SEO_CANONICAL_URL",
            ),
            (
                (
                    '    <link rel="canonical" '
                    'href="https://other.test/'
                    'site/index.html" />\n'
                ),
                "SEO_CANONICAL_URL",
            ),
            (
                (
                    '    <link rel="canonical" '
                    'href="https://www.client.test/'
                    'site/index.html?" />\n'
                ),
                "SEO_CANONICAL_URL",
            ),
            (
                (
                    '    <link rel="canonical" '
                    'href="https://www.client.test/'
                    'site/index.html#" />\n'
                ),
                "SEO_CANONICAL_URL",
            ),
        )

        for index, (
            replacement,
            expected_rule,
        ) in enumerate(cases):
            with self.subTest(
                expected_rule=expected_rule
            ):
                root = (
                    self.temporary_root
                    / f"canonical-{index}"
                )
                fixture = (
                    PublicReleaseFixture(
                        root
                    )
                )
                path = fixture.html()
                content = path.read_text(
                    encoding="utf-8"
                )
                original = (
                    '    <link rel="canonical" '
                    'href="https://www.client.test/'
                    'site/index.html" />\n'
                )
                path.write_text(
                    content.replace(
                        original,
                        replacement,
                    ),
                    encoding="utf-8",
                )
                _, findings = (
                    public_release_check
                    .inspect_public_root(
                        root=root,
                        base_url=self.base_url,
                        html_validator=(
                            no_html_violations
                        ),
                    )
                )
                self.assertIn(
                    expected_rule,
                    {
                        finding.rule_id
                        for finding in findings
                    },
                )

    def test_shared_strict_url_validation(
        self,
    ) -> None:
        invalid_values = (
            "https://exa mple.test/site/",
            "https://exa\tmple.test/site/",
            "https://www.client.test:/site/",
            "https://www.client.test/site/%",
            "https://www.client.test/site/%GG",
        )

        for value in invalid_values:
            with self.subTest(
                invalid=value
            ):
                self.assertIsNotNone(
                    public_release_check
                    .public_https_url_error(
                        value,
                        base_url=self.base_url,
                        require_site_location=True,
                        forbid_query_and_fragment=True,
                    )
                )

        ipv6_base = (
            public_release_check
            .normalize_base_url(
                (
                    "https://[2001:db8::1]:443/"
                    "日本語/"
                )
            )
        )
        self.assertEqual(
            (
                "https",
                "2001:db8::1",
                443,
            ),
            ipv6_base.origin,
        )
        self.assertEqual(
            "/日本語/",
            ipv6_base.path_prefix,
        )
        self.assertIsNone(
            public_release_check
            .public_https_url_error(
                (
                    "https://[2001:db8::1]/"
                    "%E6%97%A5%E6%9C%AC%E8%AA%9E/"
                    "index.html"
                ),
                base_url=ipv6_base,
                require_site_location=True,
                forbid_query_and_fragment=True,
            )
        )

    def test_ogp_missing_is_detected(
        self,
    ) -> None:
        path = self.fixture.html()
        lines = [
            line
            for line in path.read_text(
                encoding="utf-8"
            ).splitlines()
            if 'property="og:' not in line
        ]
        path.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        rules = set(
            self.rule_ids()
        )

        self.assertTrue(
            {
                "SEO_OG_TITLE_COUNT",
                "SEO_OG_DESCRIPTION_COUNT",
                "SEO_OG_URL_COUNT",
                "SEO_OG_IMAGE_COUNT",
            }.issubset(rules)
        )

    def test_duplicate_seo_meta_is_detected(
        self,
    ) -> None:
        self.fixture.html(
            head=(
                '    <meta name="description" '
                'content="重複説明" />\n'
                '    <meta property="og:title" '
                'content="重複OGP" />'
            )
        )

        rules = self.rule_ids()

        self.assertIn(
            "SEO_DESCRIPTION_COUNT",
            rules,
        )
        self.assertIn(
            "SEO_OG_TITLE_COUNT",
            rules,
        )

    def test_missing_html_image_css_and_js_are_detected(
        self,
    ) -> None:
        self.fixture.html(
            head=(
                '    <link rel="stylesheet" '
                'href="./missing.css" />'
            ),
            body=(
                '      <a href="./missing.html">'
                "missing</a>\n"
                '      <img src="./missing.webp" '
                'alt="" />\n'
                '      <script src="./missing.js">'
                "</script>"
            ),
        )

        missing_reasons = [
            finding.reason
            for finding in self.inspect()[1]
            if (
                finding.rule_id
                == (
                    "INTERNAL_REFERENCE_MISSING"
                )
            )
        ]

        for expected in (
            "missing.html",
            "missing.webp",
            "missing.css",
            "missing.js",
        ):
            with self.subTest(
                expected=expected
            ):
                self.assertTrue(
                    any(
                        expected in reason
                        for reason
                        in missing_reasons
                    )
                )

    def test_srcset_poster_and_existing_internal_references(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '      <a href="./about/">about</a>\n'
                '      <a href="/site/index.html#top">'
                "top</a>\n"
                '      <img src="./assets/main.webp" '
                'srcset="./assets/main.webp 1x, '
                './assets/main-2x.webp 2x" '
                'alt="" />\n'
                '      <video poster="./assets/poster.webp">'
                "<track kind=\"captions\" /></video>"
            ),
        )
        self.fixture.html(
            relative_path=(
                "about/index.html"
            )
        )
        assets = self.root / "assets"
        assets.mkdir()
        for name in (
            "main.webp",
            "main-2x.webp",
            "poster.webp",
        ):
            (
                assets
                / name
            ).write_bytes(b"asset")

        rules = self.rule_ids()

        self.assertNotIn(
            "INTERNAL_REFERENCE_MISSING",
            rules,
        )
        self.assertNotIn(
            "FRAGMENT_MISSING",
            rules,
        )

    def test_missing_same_page_fragment_is_detected(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '      <a href="#missing">'
                "missing</a>"
            )
        )

        self.assertIn(
            "FRAGMENT_MISSING",
            self.rule_ids(),
        )

    def test_decoded_parent_reference_is_rejected(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '<a href="%2e%2e/secret.html">'
                "outside</a>"
            )
        )

        self.assertIn(
            (
                "INTERNAL_REFERENCE_"
                "OUTSIDE_ROOT"
            ),
            self.rule_ids(),
        )

    def test_parent_reference_within_root_is_allowed(
        self,
    ) -> None:
        self.fixture.html()
        self.fixture.html(
            relative_path=(
                "company/about.html"
            ),
            body=(
                '<a href="../index.html">'
                "home</a>"
            ),
        )

        rules = self.rule_ids()

        self.assertNotIn(
            (
                "INTERNAL_REFERENCE_"
                "OUTSIDE_ROOT"
            ),
            rules,
        )
        self.assertNotIn(
            "INTERNAL_REFERENCE_MISSING",
            rules,
        )

    def test_forbidden_files_and_transaction_artifacts(
        self,
    ) -> None:
        self.fixture.html()
        for name in (
            ".env.production",
            "server.pem",
            "archive.tar.gz",
            "project-manifest.json",
            ".dist.tmp-orphan",
        ):
            (
                self.root
                / name
            ).write_text(
                "secret\n",
                encoding="utf-8",
            )
        (
            self.root
            / "node_modules"
        ).mkdir()
        (
            self.root
            / ".sample.wp-failed-orphan"
        ).mkdir()

        rules = self.rule_ids()

        self.assertIn(
            "FORBIDDEN_FILE",
            rules,
        )
        self.assertIn(
            (
                "FORBIDDEN_TRANSACTION_"
                "ARTIFACT"
            ),
            rules,
        )
        self.assertGreaterEqual(
            rules.count(
                (
                    "FORBIDDEN_TRANSACTION_"
                    "ARTIFACT"
                )
            ),
            2,
        )
        self.assertIn(
            "FORBIDDEN_DIRECTORY",
            rules,
        )

    def test_junction_detection_prunes_its_contents(
        self,
    ) -> None:
        self.fixture.html()
        junction = (
            self.root
            / "linked-content"
        )
        junction.mkdir()
        (
            junction
            / "should-not-scan.csv"
        ).write_text(
            "https://example.com\n",
            encoding="utf-8",
        )

        with patch.object(
            public_release_check,
            "dir_entry_is_junction",
            side_effect=(
                lambda entry: (
                    entry.name
                    == "linked-content"
                )
            ),
        ):
            findings = self.inspect()[1]

        self.assertTrue(
            any(
                finding.relative_path
                == "linked-content"
                and finding.rule_id
                == "JUNCTION_UNCHECKED"
                for finding in findings
            )
        )
        self.assertFalse(
            any(
                finding.relative_path.startswith(
                    "linked-content/"
                )
                for finding in findings
            )
        )

    def test_invalid_utf8_is_detected(
        self,
    ) -> None:
        self.fixture.html()
        (
            self.root
            / "invalid.js"
        ).write_bytes(
            b"\xff\xfe"
        )

        self.assertIn(
            "TEXT_INVALID_UTF8",
            self.rule_ids(),
        )

    def test_html_validate_violation_is_detected(
        self,
    ) -> None:
        path = self.fixture.html(
            body=(
                '      <img src="missing.webp">'
            )
        )

        findings = (
            public_release_check
            .run_html_validate(
                self.root.resolve(),
                [path.resolve()],
            )
        )

        self.assertTrue(
            any(
                finding.rule_id.startswith(
                    "HTML_VALIDATE/"
                )
                for finding in findings
            )
        )
        self.assertTrue(
            any(
                finding.line > 0
                for finding in findings
            )
        )

    def test_missing_html_validate_is_not_skipped(
        self,
    ) -> None:
        self.fixture.html()
        stderr = io.StringIO()

        with (
            patch.object(
                public_release_check,
                "html_validate_environment",
                side_effect=(
                    public_release_check
                    .PublicReleaseUsageError(
                        "local html-validate missing"
                    )
                ),
            ),
            contextlib.redirect_stderr(
                stderr
            ),
        ):
            code = (
                public_release_check.main(
                    [
                        "--root",
                        str(self.root),
                        "--base-url",
                        BASE_URL,
                    ]
                )
            )

        self.assertEqual(2, code)
        self.assertIn(
            "local html-validate missing",
            stderr.getvalue(),
        )

    def test_javascript_link_is_detected(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                '<a href="javascript:void(0)">'
                "invalid</a>"
            )
        )

        self.assertIn(
            "JAVASCRIPT_URL",
            self.rule_ids(),
        )

    def test_nonexistent_root_returns_code_two(
        self,
    ) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(
            stderr
        ):
            code = (
                public_release_check.main(
                    [
                        "--root",
                        str(
                            self.root
                            / "missing"
                        ),
                        "--base-url",
                        BASE_URL,
                    ],
                    html_validator=(
                        no_html_violations
                    ),
                )
            )

        self.assertEqual(2, code)
        self.assertIn(
            "使用上のエラー",
            stderr.getvalue(),
        )

    def test_invalid_base_url_returns_code_two(
        self,
    ) -> None:
        self.fixture.html()

        for value in (
            "http://www.client.test/",
            "https://user@www.client.test/",
            "https://www.client.test/?draft=1",
            "https://www.client.test/#draft",
            "https://www.client.test/?",
            "https://www.client.test/#",
            "https://exa mple.test/",
            "https://exa\nmple.test/",
            "https://www.client.test:/",
            "https://www.client.test/%",
            "https://www.client.test/%GG",
        ):
            with self.subTest(value=value):
                with (
                    contextlib
                    .redirect_stderr(
                        io.StringIO()
                    )
                ):
                    code = (
                        public_release_check
                        .main(
                            [
                                "--root",
                                str(self.root),
                                "--base-url",
                                value,
                            ],
                            html_validator=(
                                no_html_violations
                            ),
                        )
                    )
                self.assertEqual(2, code)

    def test_zero_html_is_not_success(
        self,
    ) -> None:
        (
            self.root
            / "style.css"
        ).write_text(
            "body {}\n",
            encoding="utf-8",
        )

        html_count, findings = (
            self.inspect()
        )

        self.assertEqual(0, html_count)
        self.assertIn(
            "NO_HTML_FILES",
            {
                finding.rule_id
                for finding in findings
            },
        )

    def test_all_findings_are_reported_in_fixed_order(
        self,
    ) -> None:
        self.fixture.html(
            body=(
                "      <p>20XX 〇〇 "
                "example.com</p>\n"
                '      <form action="#"></form>'
            )
        )

        first = self.inspect()[1]
        second = self.inspect()[1]

        self.assertGreaterEqual(
            len(first),
            4,
        )
        self.assertEqual(
            [
                finding.format()
                for finding in first
            ],
            [
                finding.format()
                for finding in second
            ],
        )
        self.assertEqual(
            first,
            sorted(
                first,
                key=lambda finding: (
                    finding.sort_key()
                ),
            ),
        )

    def test_success_and_finding_exit_codes(
        self,
    ) -> None:
        self.fixture.html()
        stdout = io.StringIO()

        with contextlib.redirect_stdout(
            stdout
        ):
            success_code = (
                public_release_check.main(
                    [
                        "--root",
                        str(self.root),
                        "--base-url",
                        BASE_URL,
                    ],
                    html_validator=(
                        no_html_violations
                    ),
                )
            )

        self.assertEqual(0, success_code)
        self.assertIn(
            "対象HTML: 1件",
            stdout.getvalue(),
        )

        path = self.root / "index.html"
        path.write_text(
            path.read_text(
                encoding="utf-8"
            ).replace(
                "公開案件</h1>",
                "20XX</h1>",
            ),
            encoding="utf-8",
        )
        stdout = io.StringIO()

        with contextlib.redirect_stdout(
            stdout
        ):
            finding_code = (
                public_release_check.main(
                    [
                        "--root",
                        str(self.root),
                        "--base-url",
                        BASE_URL,
                    ],
                    html_validator=(
                        no_html_violations
                    ),
                )
            )

        self.assertEqual(1, finding_code)
        self.assertIn(
            "検出件数:",
            stdout.getvalue(),
        )

    def snapshot(
        self,
    ) -> tuple[
        tuple[str, ...],
        dict[str, tuple[int, bytes]],
    ]:
        paths = tuple(
            sorted(
                path.relative_to(
                    self.root
                ).as_posix()
                for path in (
                    self.root.rglob("*")
                )
            )
        )
        files = {
            path.relative_to(
                self.root
            ).as_posix(): (
                path.stat().st_mtime_ns,
                path.read_bytes(),
            )
            for path in self.root.rglob("*")
            if path.is_file()
        }
        return paths, files

    def test_check_is_read_only(
        self,
    ) -> None:
        self.fixture.html()
        (
            self.root
            / "assets"
        ).mkdir()
        (
            self.root
            / "assets"
            / "image.webp"
        ).write_bytes(b"image")
        before = self.snapshot()

        self.inspect()

        self.assertEqual(
            before,
            self.snapshot(),
        )

    def test_spaces_and_japanese_paths_are_preserved(
        self,
    ) -> None:
        self.fixture.html(
            relative_path=(
                "会社 情報/案内 ページ.html"
            ),
            body=(
                "      <p>20XX</p>"
            ),
        )
        stdout = io.StringIO()

        with contextlib.redirect_stdout(
            stdout
        ):
            code = (
                public_release_check.main(
                    [
                        "--root",
                        str(self.root),
                        "--base-url",
                        BASE_URL,
                    ],
                    html_validator=(
                        no_html_violations
                    ),
                )
            )

        self.assertEqual(1, code)
        self.assertIn(
            "会社 情報/案内 ページ.html",
            stdout.getvalue(),
        )
        self.assertIn(
            "DUMMY_YEAR",
            stdout.getvalue(),
        )

    def test_cli_emits_japanese_path_as_utf8(
        self,
    ) -> None:
        self.fixture.html(
            relative_path=(
                "会社 情報/案内 ページ.html"
            ),
            body=(
                "      <p>20XX</p>"
            ),
        )
        checker = (
            Path(__file__).resolve()
            .parents[1]
            / "tools"
            / "public_release_check.py"
        )

        result = subprocess.run(
            [
                sys.executable,
                str(checker),
                "--root",
                str(self.root),
                "--base-url",
                BASE_URL,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn(
            "会社 情報/案内 ページ.html",
            result.stdout,
        )
        self.assertIn(
            "DUMMY_YEAR",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
