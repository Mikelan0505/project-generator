from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import convert_to_wp
import script

try:
    from .test_template_accordion import (
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
    )
    from .test_template_cta import (
        body_classes,
        cta_contract_errors,
        expectations_by_path,
        generated_regression_errors,
    )
    from .test_template_references import (
        form_accessibility_errors,
        product_listing_contract_errors,
    )
except ImportError:
    from test_template_accordion import (
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
    )
    from test_template_cta import (
        body_classes,
        cta_contract_errors,
        expectations_by_path,
        generated_regression_errors,
    )
    from test_template_references import (
        form_accessibility_errors,
        product_listing_contract_errors,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
STARTER_ROOT = REPOSITORY_ROOT.parent / "sass-starter-exiga"
EXPECTED_TEMPLATE_PATHS = (
    "lp/index.html",
    "shop/about.html",
    "shop/contact.html",
    "shop/index.html",
    "shop/products.html",
    "website/about.html",
    "website/contact.html",
    "website/index.html",
    "website/service.html",
)
CANONICAL_BOOTSTRAP = """\
document.documentElement.classList.add('has-js');
window.addEventListener('load', () => {
if (document.documentElement.dataset.revealReady !== 'true') {
document.documentElement.classList.remove('has-js');
}
});"""
EXPECTED_REVEAL_SNAPSHOT = (
    (
        "li",
        (
            "flow-list__item",
            "js-reveal",
            "u-reveal",
            "u-reveal-up",
        ),
        "flow-title",
        ("flow-list",),
        "ヒアリング",
        "要件、課題、優先順位を確認します。",
    ),
    (
        "li",
        (
            "flow-list__item",
            "js-reveal",
            "u-reveal",
            "u-reveal-up",
        ),
        "flow-title",
        ("flow-list",),
        "提案",
        "進め方、内容、概算、体制などを整理して提示します。",
    ),
    (
        "li",
        (
            "flow-list__item",
            "js-reveal",
            "u-reveal",
            "u-reveal-up",
        ),
        "flow-title",
        ("flow-list",),
        "制作・実行",
        "決定内容に沿って制作や実作業を進行します。",
    ),
    (
        "li",
        (
            "flow-list__item",
            "js-reveal",
            "u-reveal",
            "u-reveal-up",
        ),
        "flow-title",
        ("flow-list",),
        "納品・運用",
        "公開後や導入後の運用支援がある場合はここに記載します。",
    ),
)


@dataclass
class ScriptRecord:
    attrs: dict[str, str | None]
    order: int
    in_head: bool
    data: list[str] = field(default_factory=list)

    @property
    def source(self) -> str:
        return "".join(self.data)


class HeadContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.order = 0
        self.scripts: list[ScriptRecord] = []
        self.stylesheet_orders: list[int] = []
        self.current_script: ScriptRecord | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        attributes = dict(attrs)
        self.order += 1
        in_head = "head" in self.stack

        if normalized_tag == "script":
            record = ScriptRecord(
                attrs=attributes,
                order=self.order,
                in_head=in_head,
            )
            self.scripts.append(record)
            self.current_script = record

        if normalized_tag == "link" and "stylesheet" in (
            attributes.get("rel") or ""
        ).lower().split():
            self.stylesheet_orders.append(self.order)

        if normalized_tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(normalized_tag)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1] == tag.lower():
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if self.current_script is not None:
            self.current_script.data.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()

        if normalized_tag == "script":
            self.current_script = None

        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == normalized_tag:
                del self.stack[index:]
                break


def parse_head_contract(text: str) -> HeadContractParser:
    parser = HeadContractParser()
    parser.feed(text)
    parser.close()
    return parser


def normalize_script(source: str) -> str:
    return "\n".join(
        line.strip()
        for line in source.strip().splitlines()
        if line.strip()
    )


def is_bootstrap_candidate(record: ScriptRecord) -> bool:
    source = record.source
    return any(
        marker in source
        for marker in (
            "document.documentElement",
            "has-js",
            "revealReady",
            "data-reveal-ready",
        )
    )


def bootstrap_records(text: str) -> list[ScriptRecord]:
    return [
        record
        for record in parse_head_contract(text).scripts
        if is_bootstrap_candidate(record)
    ]


def bootstrap_contract_errors(text: str) -> list[str]:
    parser = parse_head_contract(text)
    records = [
        record
        for record in parser.scripts
        if is_bootstrap_candidate(record)
    ]
    errors: list[str] = []

    if len(records) != 1:
        errors.append(
            "bootstrap-count:"
            f"expected=1 actual={len(records)}"
        )

    if not records:
        return errors

    bootstrap = records[0]
    source = bootstrap.source

    if not bootstrap.in_head:
        errors.append("bootstrap:not-in-head")

    if parser.stylesheet_orders and bootstrap.order >= min(
        parser.stylesheet_orders
    ):
        errors.append("bootstrap:not-before-stylesheet")

    module_orders = [
        record.order
        for record in parser.scripts
        if (record.attrs.get("type") or "").lower()
        == "module"
    ]
    if module_orders and bootstrap.order >= min(module_orders):
        errors.append("bootstrap:not-before-module")

    semantic_patterns = {
        "missing-has-js-add": (
            r"document\.documentElement\.classList\.add"
            r"\(\s*['\"]has-js['\"]\s*\)"
        ),
        "missing-reveal-ready-check": (
            r"document\.documentElement\.dataset\.revealReady"
            r"\s*!==\s*['\"]true['\"]"
        ),
        "missing-fail-open": (
            r"document\.documentElement\.classList\.remove"
            r"\(\s*['\"]has-js['\"]\s*\)"
        ),
        "missing-load-handler": (
            r"window\.addEventListener"
            r"\(\s*['\"]load['\"]"
        ),
    }
    for error, pattern in semantic_patterns.items():
        if not re.search(pattern, source):
            errors.append(error)

    if normalize_script(source) != CANONICAL_BOOTSTRAP:
        errors.append("bootstrap:not-canonical")

    return errors


def bootstrap_collection_errors(
    documents: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    snippets: dict[str, str] = {}

    for name, text in documents.items():
        errors.extend(
            f"{name}:{error}"
            for error in bootstrap_contract_errors(text)
        )
        records = bootstrap_records(text)
        if len(records) == 1:
            snippets[name] = normalize_script(
                records[0].source
            )

    if len(set(snippets.values())) > 1:
        errors.append("bootstrap:template-snippets-differ")

    return errors


def nearest_ancestor(element, tag: str):
    parent = element.parent
    while parent is not None:
        if parent.tag == tag:
            return parent
        parent = parent.parent
    return None


def class_text(element, class_name: str) -> str:
    matches = elements_with_class(element, class_name)
    return visible_text(matches[0]) if len(matches) == 1 else ""


def reveal_snapshot(text: str) -> tuple[tuple[object, ...], ...]:
    document = parse_document(text)
    targets = elements_with_class(document, "js-reveal")
    snapshot: list[tuple[object, ...]] = []

    for target in targets:
        section = nearest_ancestor(target, "section")
        parent = target.parent
        snapshot.append(
            (
                target.tag,
                tuple(sorted(target.classes)),
                (
                    section.attrs.get("aria-labelledby")
                    if section is not None
                    else None
                ),
                (
                    tuple(sorted(parent.classes))
                    if parent is not None
                    else ()
                ),
                class_text(target, "flow-list__title"),
                class_text(target, "flow-list__text"),
            )
        )

    return tuple(snapshot)


def reveal_snapshot_errors(text: str) -> list[str]:
    actual = reveal_snapshot(text)
    errors: list[str] = []

    if len(actual) != len(EXPECTED_REVEAL_SNAPSHOT):
        errors.append(
            "reveal-target-count:"
            f"expected={len(EXPECTED_REVEAL_SNAPSHOT)} "
            f"actual={len(actual)}"
        )

    if actual != EXPECTED_REVEAL_SNAPSHOT:
        errors.append("reveal-target-snapshot-mismatch")

    return errors


def valid_fixture(bootstrap: str) -> str:
    return f"""\
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <script>
      {bootstrap}
    </script>
    <link rel="stylesheet" href="./dist/css/main.css" />
  </head>
  <body>
    <script type="module" src="./dist/js/core/app.js"></script>
  </body>
</html>
"""


class TemplateRevealTests(unittest.TestCase):
    def test_all_template_html_uses_canonical_early_bootstrap(
        self,
    ) -> None:
        paths = sorted(TEMPLATES_ROOT.rglob("*.html"))
        relative_paths = tuple(
            path.relative_to(TEMPLATES_ROOT).as_posix()
            for path in paths
        )
        self.assertEqual(EXPECTED_TEMPLATE_PATHS, relative_paths)
        documents = {
            path.relative_to(TEMPLATES_ROOT).as_posix(): (
                path.read_text(encoding="utf-8")
            )
            for path in paths
        }
        self.assertEqual(
            [],
            bootstrap_collection_errors(documents),
        )

    def test_bootstrap_validator_rejects_invalid_contracts(
        self,
    ) -> None:
        script_tag = (
            "<script>\n      "
            f"{CANONICAL_BOOTSTRAP}\n"
            "    </script>"
        )
        valid = valid_fixture(CANONICAL_BOOTSTRAP)
        invalid_cases = {
            "missing": valid.replace(script_tag, "", 1),
            "duplicate": valid.replace(
                script_tag,
                f"{script_tag}\n{script_tag}",
                1,
            ),
            "outside-head": valid.replace(
                script_tag,
                "",
                1,
            ).replace("<body>", f"<body>\n{script_tag}", 1),
            "after-stylesheet": valid.replace(
                f"{script_tag}\n"
                '    <link rel="stylesheet"',
                '    <link rel="stylesheet"',
                1,
            ).replace(
                'href="./dist/css/main.css" />',
                f'href="./dist/css/main.css" />\n    {script_tag}',
                1,
            ),
            "after-module": valid.replace(
                "    <script>\n",
                (
                    '<script type="module" '
                    'src="./early.js"></script>\n'
                    "    <script>\n"
                ),
                1,
            ),
            "missing-has-js": valid.replace(
                "document.documentElement.classList.add('has-js');",
                "",
                1,
            ),
            "missing-ready": valid.replace(
                "document.documentElement.dataset.revealReady !== 'true'",
                "true",
                1,
            ),
            "missing-fail-open": valid.replace(
                "document.documentElement.classList.remove('has-js');",
                "",
                1,
            ),
            "missing-load": valid.replace(
                "window.addEventListener('load'",
                "window.addEventListener('DOMContentLoaded'",
                1,
            ),
            "runtime-class-drift": valid.replace(
                "has-js",
                "javascript-enabled",
            ),
        }

        self.assertEqual(
            [],
            bootstrap_contract_errors(valid),
        )
        for name, fixture in invalid_cases.items():
            with self.subTest(name=name):
                self.assertTrue(
                    bootstrap_contract_errors(fixture),
                    name,
                )

        drifted = valid.replace(
            "window.addEventListener('load', () => {",
            (
                "// template-specific drift\n"
                "window.addEventListener('load', () => {"
            ),
            1,
        )
        self.assertIn(
            "bootstrap:template-snippets-differ",
            bootstrap_collection_errors(
                {"a.html": valid, "b.html": drifted}
            ),
        )

    def test_website_service_reveal_snapshot_is_unchanged(
        self,
    ) -> None:
        source = (
            TEMPLATES_ROOT / "website" / "service.html"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            [],
            reveal_snapshot_errors(source),
        )

        reduced = source.replace(" js-reveal", "", 1)
        self.assertIn(
            "reveal-target-count:expected=4 actual=3",
            reveal_snapshot_errors(reduced),
        )

    def test_starter_reveal_semantics_match_bootstrap_contract(
        self,
    ) -> None:
        canonical_html = (
            STARTER_ROOT / "src/html/arch-corp-index.html"
        ).read_text(encoding="utf-8")
        records = bootstrap_records(canonical_html)
        self.assertEqual(1, len(records))
        self.assertEqual(
            CANONICAL_BOOTSTRAP,
            normalize_script(records[0].source),
        )
        self.assertEqual(
            [],
            bootstrap_contract_errors(canonical_html),
        )

        docs = (
            STARTER_ROOT / "docs/components/reveal-motion.md"
        ).read_text(encoding="utf-8")
        scss = (
            STARTER_ROOT
            / "src/scss/utilities/_reveal.scss"
        ).read_text(encoding="utf-8")
        app = (
            STARTER_ROOT / "src/js/core/app.js"
        ).read_text(encoding="utf-8")
        compiled_css = (
            STARTER_ROOT / "dist/css/main.css"
        ).read_text(encoding="utf-8")

        self.assertIn("`.has-js` activates Reveal", docs)
        self.assertIn("Without `.has-js`", docs)
        self.assertIn("prefers-reduced-motion: reduce", docs)
        self.assertRegex(scss, r"\.has-js\s+\.u-reveal\s*\{")
        self.assertRegex(
            scss,
            r"html:not\(\.has-js\)\s+\.js-reveal\s*\{",
        )
        self.assertRegex(
            scss,
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)",
        )
        self.assertIn("opacity: var(--reveal-opacity-end) !important", scss)
        self.assertIn("transition: none !important", scss)
        self.assertIn("document.querySelector('.js-reveal')", app)
        self.assertRegex(
            app,
            r"if\s*\(revealReady\)\s*\{\s*"
            r"document\.documentElement\.dataset\.revealReady"
            r"\s*=\s*['\"]true['\"]",
        )
        self.assertIn(".has-js .js-reveal:not(.is-inview)", compiled_css)
        self.assertIn("html:not(.has-js) .js-reveal", compiled_css)

    def test_generated_templates_preserve_reveal_and_prior_contracts(
        self,
    ) -> None:
        expected_actions = expectations_by_path()

        with tempfile.TemporaryDirectory(
            prefix="pg-html-005-"
        ) as temp:
            temp_path = Path(temp)

            for template_name in ("website", "shop", "lp"):
                base_dir = (
                    temp_path
                    / template_name
                    / "project-generator"
                )
                shutil.copytree(
                    TEMPLATES_ROOT / template_name,
                    base_dir / "templates" / template_name,
                )
                starter_dist = STARTER_ROOT / "dist"

                with patch.object(
                    script,
                    "resolve_exiga_dist",
                    return_value=starter_dist,
                ):
                    output_dir = script.create_project(
                        base_dir=base_dir,
                        template_name=template_name,
                        project_name=(
                            f"{template_name} Reveal Contract"
                        ),
                        force=True,
                    )

                generated_documents: dict[str, str] = {}
                for html_path in sorted(
                    output_dir.rglob("*.html")
                ):
                    relative_path = html_path.relative_to(
                        output_dir
                    ).as_posix()
                    source_path = (
                        f"{template_name}/{relative_path}"
                    )
                    text = html_path.read_text(encoding="utf-8")
                    generated_documents[source_path] = text
                    self.assertTrue(
                        {
                            f"t-{template_name}",
                            (
                                "p-home"
                                if html_path.stem == "index"
                                else f"p-{html_path.stem}"
                            ),
                        }.issubset(body_classes(text))
                    )
                    self.assertEqual(
                        [],
                        form_accessibility_errors(
                            text,
                            source_name=source_path,
                        ),
                    )
                    self.assertEqual(
                        [],
                        cta_contract_errors(
                            text,
                            expected_actions.get(source_path, ()),
                        ),
                        source_path,
                    )

                self.assertEqual(
                    [],
                    bootstrap_collection_errors(
                        generated_documents
                    ),
                )
                self.assertEqual(
                    [],
                    generated_reference_errors(output_dir),
                )
                self.assertEqual(
                    [],
                    generated_regression_errors(
                        template_name,
                        output_dir,
                    ),
                )

                if template_name == "website":
                    self.assertEqual(
                        EXPECTED_REVEAL_SNAPSHOT,
                        reveal_snapshot(
                            generated_documents[
                                "website/service.html"
                            ]
                        ),
                    )

                if template_name == "shop":
                    self.assertEqual(
                        [],
                        product_listing_contract_errors(
                            generated_documents[
                                "shop/products.html"
                            ],
                            expected_grid_count=3,
                            expected_product_count=21,
                        ),
                    )

                for relative_path in (
                    Path("css/main.css"),
                    Path("js/core/app.js"),
                ):
                    self.assertEqual(
                        (starter_dist / relative_path).read_bytes(),
                        (
                            output_dir / "dist" / relative_path
                        ).read_bytes(),
                    )

        self.assertFalse(temp_path.exists())

    def test_wordpress_conversion_preserves_bootstrap_once(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="pg-html-005-wp-"
        ) as temp:
            base_dir = Path(temp) / "project-generator"
            shutil.copytree(
                TEMPLATES_ROOT / "website",
                base_dir / "templates" / "website",
            )
            shutil.copytree(
                REPOSITORY_ROOT / "wp-stubs",
                base_dir / "wp-stubs",
            )

            with patch.object(
                script,
                "resolve_exiga_dist",
                return_value=STARTER_ROOT / "dist",
            ):
                output_dir = script.create_project(
                    base_dir=base_dir,
                    template_name="website",
                    project_name="Reveal WordPress Contract",
                    force=True,
                )

            project_dir, generated_files = (
                convert_to_wp.convert_project(
                    base_dir=base_dir,
                    project_name=output_dir.name,
                    template_name="website",
                )
            )
            header = (project_dir / "header.php").read_text(
                encoding="utf-8"
            )
            self.assertEqual(
                [],
                bootstrap_contract_errors(header),
            )
            self.assertIn("<?php wp_head(); ?>", header)

            page_php_paths = sorted(
                path
                for path in project_dir.glob("*.php")
                if path.name not in {
                    "header.php",
                    "footer.php",
                    "functions.php",
                }
            )
            for path in page_php_paths:
                self.assertEqual(
                    [],
                    bootstrap_records(
                        path.read_text(encoding="utf-8")
                    ),
                    path.name,
                )

            for required in (
                "style.css",
                "functions.php",
                "header.php",
                "footer.php",
            ):
                self.assertTrue((project_dir / required).is_file())
                self.assertIn(required, generated_files)

            self.assertEqual(
                (),
                convert_to_wp.filesystem_safety
                .find_project_transaction_artifacts(project_dir),
            )


if __name__ == "__main__":
    unittest.main()
