from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

import convert_to_wp
import filesystem_safety
import script

try:
    from .test_template_accordion import (
        direct_children_with_class,
        element_children,
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
    )
    from .test_template_class_contracts import (
        document_contract_errors,
        page_class_for,
    )
    from .test_template_cta import (
        body_classes,
        css_rule_bodies,
        cta_contract_errors,
        expectations_by_path,
        generated_regression_errors,
        has_declaration,
    )
    from .test_template_references import (
        form_accessibility_errors,
        product_listing_contract_errors,
    )
    from .test_template_reveal import (
        bootstrap_collection_errors,
    )
except ImportError:
    from test_template_accordion import (
        direct_children_with_class,
        element_children,
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
    )
    from test_template_class_contracts import (
        document_contract_errors,
        page_class_for,
    )
    from test_template_cta import (
        body_classes,
        css_rule_bodies,
        cta_contract_errors,
        expectations_by_path,
        generated_regression_errors,
        has_declaration,
    )
    from test_template_references import (
        form_accessibility_errors,
        product_listing_contract_errors,
    )
    from test_template_reveal import (
        bootstrap_collection_errors,
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
FORBIDDEN_FOOTER_CLASSES = {
    "footer__info",
    "footer__info-link",
    "footer__info-title",
}
STANDARD_FOOTER_CLASSES = {
    "footer__brand",
    "footer__copy",
    "footer__cta",
    "footer__desc",
    "footer__links",
    "footer__meta",
    "footer__nav",
    "footer__title",
    "footer__top",
}

LinkSnapshot = tuple[str, str]


@dataclass(frozen=True)
class FooterExpectation:
    description: str
    navigation: tuple[LinkSnapshot, ...]
    cta_heading: str | None = None
    cta_link: LinkSnapshot | None = None


WEBSITE_NAVIGATION = (
    ("./index.html", "トップ"),
    ("./about.html", "会社案内"),
    ("./service.html", "サービス"),
    ("./contact.html", "お問い合わせ"),
)
SHOP_NAVIGATION = (
    ("./index.html", "トップ"),
    ("./products.html", "商品一覧"),
    ("./about.html", "店舗案内"),
    ("./contact.html", "お問い合わせ"),
)
FOOTER_EXPECTATIONS = {
    "website/index.html": FooterExpectation(
        "仕事用スターターとして最初の構成を整えた状態です。必要な情報へ差し替えて利用します。",
        WEBSITE_NAVIGATION,
    ),
    "website/about.html": FooterExpectation(
        "会社案内テンプレとして最低限の説明枠を用意しています。",
        WEBSITE_NAVIGATION,
    ),
    "website/service.html": FooterExpectation(
        "サービス紹介ページの最小構成を用意したスターターテンプレです。",
        WEBSITE_NAVIGATION,
    ),
    "website/contact.html": FooterExpectation(
        "最小構成の問い合わせページスターターです。",
        WEBSITE_NAVIGATION,
        cta_heading="Quick Links",
        cta_link=("./index.html", "トップへ戻る"),
    ),
    "shop/index.html": FooterExpectation(
        "店舗・物販向けスターターとして商品と店舗情報を整理しやすい構成です。",
        SHOP_NAVIGATION,
    ),
    "shop/about.html": FooterExpectation(
        "店舗紹介テンプレとして背景・こだわり・営業時間を整理しやすい構成です。",
        SHOP_NAVIGATION,
    ),
    "shop/products.html": FooterExpectation(
        "商品紹介テンプレとしてカテゴリと価格を整理しやすい構成です。",
        SHOP_NAVIGATION,
    ),
    "shop/contact.html": FooterExpectation(
        "店舗向け問い合わせスターターとして最小構成に整理しています。",
        SHOP_NAVIGATION,
        cta_heading="Quick Links",
        cta_link=("./products.html", "商品一覧を見る"),
    ),
    "lp/index.html": FooterExpectation(
        "仕事用 LP の最小スターターとして使うための土台です。",
        (
            ("#problem", "課題"),
            ("#solution", "特徴"),
            ("#offer", "提供内容"),
            ("#faq", "FAQ"),
        ),
        cta_heading="お問い合わせ",
        cta_link=("#cta", "お問い合わせ導線へ"),
    ),
}


def class_tokens(text: str) -> set[str]:
    return {
        class_name
        for element in walk(parse_document(text))
        for class_name in element.classes
    }


def link_snapshot(element) -> tuple[LinkSnapshot, ...]:
    return tuple(
        (
            candidate.attrs.get("href") or "",
            visible_text(candidate),
        )
        for candidate in walk(element)
        if candidate.tag == "a"
    )


def component_name(element) -> str:
    if element.tag == "h2" and element.attrs.get("id") == "footer-title":
        return "heading"

    for class_name in (
        "footer__top",
        "footer__cta",
        "footer__copy",
    ):
        if class_name in element.classes:
            return class_name

    return element.tag


def footer_contract_errors(
    text: str,
    expectation: FooterExpectation,
    *,
    project_name: str = "{{PROJECT}}",
    generated_date: str = "{{DATE}}",
) -> list[str]:
    document = parse_document(text)
    all_classes = class_tokens(text)
    errors = [
        f"forbidden-class:{class_name}"
        for class_name in sorted(
            FORBIDDEN_FOOTER_CLASSES & all_classes
        )
    ]
    errors.extend(
        f"undefined-footer-class:{class_name}"
        for class_name in sorted(
            {
                class_name
                for class_name in all_classes
                if class_name.startswith("footer__")
            }
            - STANDARD_FOOTER_CLASSES
        )
    )

    footers = [
        element
        for element in walk(document)
        if element.tag == "footer"
        and "site-footer" in element.classes
    ]
    if len(footers) != 1:
        errors.append(f"site-footer-count:{len(footers)}")
        return errors

    footer = footers[0]
    if "site-footer--standard" not in footer.classes:
        errors.append("missing-standard-modifier")
    if footer.attrs.get("aria-labelledby") != "footer-title":
        errors.append("footer-aria-labelledby")

    containers = [
        child
        for child in element_children(footer)
        if {"l-container", "c-stack"}.issubset(child.classes)
    ]
    if len(containers) != 1:
        errors.append(f"footer-container-count:{len(containers)}")
        return errors

    container = containers[0]
    container_children = element_children(container)
    expected_order = ["heading", "footer__top"]
    if expectation.cta_link is not None:
        expected_order.append("footer__cta")
    expected_order.append("footer__copy")
    actual_order = [
        component_name(child)
        for child in container_children
    ]
    if actual_order != expected_order:
        errors.append(
            "footer-child-order:"
            f"expected={expected_order} actual={actual_order}"
        )

    headings = [
        child
        for child in container_children
        if child.tag == "h2"
        and child.attrs.get("id") == "footer-title"
    ]
    if len(headings) != 1:
        errors.append(f"footer-heading-count:{len(headings)}")
    elif (
        "u-hidden" not in headings[0].classes
        or visible_text(headings[0]) != "フッター"
    ):
        errors.append("footer-heading-contract")

    tops = direct_children_with_class(container, "footer__top")
    if len(tops) != 1:
        errors.append(f"footer-top-count:{len(tops)}")
        return errors

    top = tops[0]
    top_children = element_children(top)
    top_order = [
        "footer__brand"
        if "footer__brand" in child.classes
        else "footer__nav"
        if "footer__nav" in child.classes
        else component_name(child)
        for child in top_children
    ]
    if top_order != ["footer__brand", "footer__nav"]:
        errors.append(
            "footer-top-child-order:"
            f"actual={top_order}"
        )

    brands = direct_children_with_class(top, "footer__brand")
    navs = direct_children_with_class(top, "footer__nav")
    if len(brands) != 1:
        errors.append(f"footer-brand-count:{len(brands)}")
    if len(navs) != 1:
        errors.append(f"footer-nav-count:{len(navs)}")

    if len(brands) == 1:
        brand = brands[0]
        expected_brand = {
            "footer__title": project_name,
            "footer__desc": expectation.description,
            "footer__meta": (
                "Generated from project-generator / "
                f"{generated_date}"
            ),
        }
        for class_name, expected_text in expected_brand.items():
            elements = direct_children_with_class(
                brand,
                class_name,
            )
            if len(elements) != 1:
                errors.append(
                    f"{class_name}-count:{len(elements)}"
                )
            elif visible_text(elements[0]) != expected_text:
                errors.append(f"{class_name}-snapshot")

    actual_navigation: tuple[LinkSnapshot, ...] = ()
    if len(navs) == 1:
        nav = navs[0]
        if nav.tag != "nav":
            errors.append("footer-nav-element")
        if nav.attrs.get("aria-label") != "フッターナビゲーション":
            errors.append("footer-nav-aria-label")

        lists = direct_children_with_class(nav, "footer__links")
        if len(lists) != 1 or lists[0].tag != "ul":
            errors.append(f"footer-links-count:{len(lists)}")
        else:
            list_items = element_children(lists[0])
            if any(item.tag != "li" for item in list_items):
                errors.append("footer-links-item-element")
            actual_navigation = link_snapshot(lists[0])
            if len(actual_navigation) != len(list_items):
                errors.append("footer-links-anchor-count")

        if actual_navigation != expectation.navigation:
            errors.append("footer-navigation-snapshot")

    ctas = direct_children_with_class(container, "footer__cta")
    expected_cta_count = int(expectation.cta_link is not None)
    if len(ctas) != expected_cta_count:
        errors.append(
            "footer-cta-count:"
            f"expected={expected_cta_count} actual={len(ctas)}"
        )

    actual_cta_links: tuple[LinkSnapshot, ...] = ()
    if expectation.cta_link is not None and len(ctas) == 1:
        cta_children = element_children(ctas[0])
        if (
            len(cta_children) != 2
            or any(child.tag != "p" for child in cta_children)
        ):
            errors.append("footer-cta-children")
        else:
            if visible_text(cta_children[0]) != expectation.cta_heading:
                errors.append("footer-cta-heading-snapshot")
            actual_cta_links = link_snapshot(cta_children[1])
            if actual_cta_links != (expectation.cta_link,):
                errors.append("footer-cta-link-snapshot")

    duplicates = set(actual_navigation) & set(actual_cta_links)
    if duplicates:
        errors.append(
            "duplicate-footer-links:"
            + ",".join(
                f"{href}|{label}"
                for href, label in sorted(duplicates)
            )
        )

    copies = direct_children_with_class(container, "footer__copy")
    if len(copies) != 1:
        errors.append(f"footer-copy-count:{len(copies)}")
    elif (
        [child.tag for child in element_children(copies[0])]
        != ["small"]
        or visible_text(copies[0]) != f"© {project_name}"
    ):
        errors.append("footer-copy-snapshot")

    return errors


FIXTURE_EXPECTATION = FooterExpectation(
    "Description",
    (("/", "Home"), ("/contact/", "Contact")),
    cta_heading="Support",
    cta_link=("mailto:info@example.com", "Email"),
)
VALID_FIXTURE = """\
<footer class="site-footer site-footer--standard" aria-labelledby="footer-title">
  <div class="l-container c-stack">
    <h2 id="footer-title" class="u-hidden">フッター</h2>
    <div class="footer__top">
      <div class="footer__brand c-stack c-stack--gap-16">
        <p class="footer__title">Project</p>
        <p class="footer__desc">Description</p>
        <p class="footer__meta">Generated from project-generator / 2026-01-01</p>
      </div>
      <nav class="footer__nav" aria-label="フッターナビゲーション">
        <ul class="footer__links">
          <li><a href="/">Home</a></li>
          <li><a href="/contact/">Contact</a></li>
        </ul>
      </nav>
    </div>
    <div class="footer__cta">
      <p>Support</p>
      <p><a href="mailto:info@example.com">Email</a></p>
    </div>
    <p class="footer__copy"><small>© Project</small></p>
  </div>
</footer>
"""


class TemplateFooterTests(unittest.TestCase):
    def test_all_templates_match_footer_snapshots_and_structure(
        self,
    ) -> None:
        actual_paths = tuple(
            path.relative_to(TEMPLATES_ROOT).as_posix()
            for path in sorted(TEMPLATES_ROOT.rglob("*.html"))
        )
        self.assertEqual(EXPECTED_TEMPLATE_PATHS, actual_paths)
        self.assertEqual(
            EXPECTED_TEMPLATE_PATHS,
            tuple(sorted(FOOTER_EXPECTATIONS)),
        )

        for template_path in EXPECTED_TEMPLATE_PATHS:
            with self.subTest(template_path=template_path):
                text = (
                    TEMPLATES_ROOT / template_path
                ).read_text(encoding="utf-8")
                self.assertEqual(
                    [],
                    footer_contract_errors(
                        text,
                        FOOTER_EXPECTATIONS[template_path],
                    ),
                )

    def test_footer_validator_rejects_contract_regressions(
        self,
    ) -> None:
        invalid_cases = {
            "undefined-class": (
                VALID_FIXTURE.replace(
                    "<p>Support</p>",
                    '<p class="footer__info-title">Support</p>',
                ),
                "forbidden-class:footer__info-title",
            ),
            "nav-outside-top": (
                VALID_FIXTURE.replace(
                    "      <nav class=\"footer__nav\"",
                    "    </div>\n      <nav class=\"footer__nav\"",
                    1,
                ).replace(
                    "      </nav>\n    </div>\n    <div class=\"footer__cta\">",
                    "      </nav>\n    <div class=\"footer__cta\">",
                    1,
                ),
                "footer-top-child-order",
            ),
            "wrong-top-order": (
                VALID_FIXTURE.replace(
                    '<div class="footer__brand c-stack c-stack--gap-16">',
                    '<div class="footer__nav">',
                    1,
                ).replace(
                    '<nav class="footer__nav"',
                    '<nav class="footer__brand"',
                    1,
                ),
                "footer-top-child-order",
            ),
            "duplicate-link": (
                VALID_FIXTURE.replace(
                    'href="mailto:info@example.com">Email',
                    'href="/contact/">Contact',
                    1,
                ),
                "duplicate-footer-links",
            ),
            "changed-href": (
                VALID_FIXTURE.replace(
                    'href="/contact/">Contact',
                    'href="/support/">Contact',
                    1,
                ),
                "footer-navigation-snapshot",
            ),
            "changed-text": (
                VALID_FIXTURE.replace(
                    ">Contact</a>",
                    ">Support</a>",
                    1,
                ),
                "footer-navigation-snapshot",
            ),
            "missing-nav-label": (
                VALID_FIXTURE.replace(
                    ' aria-label="フッターナビゲーション"',
                    "",
                    1,
                ),
                "footer-nav-aria-label",
            ),
            "extra-footer": (
                VALID_FIXTURE + VALID_FIXTURE,
                "site-footer-count:2",
            ),
        }

        for name, (markup, expected_error) in invalid_cases.items():
            with self.subTest(name=name):
                errors = footer_contract_errors(
                    markup,
                    FIXTURE_EXPECTATION,
                    project_name="Project",
                    generated_date="2026-01-01",
                )
                self.assertTrue(
                    any(
                        expected_error in error
                        for error in errors
                    ),
                    errors,
                )

    def test_starter_docs_scss_and_compiled_css_define_contract(
        self,
    ) -> None:
        docs = (
            STARTER_ROOT
            / "docs/patterns/footer-patterns.md"
        ).read_text(encoding="utf-8")
        structure_scss = (
            STARTER_ROOT
            / "src/scss/layouts/footer/_footer-structure.scss"
        ).read_text(encoding="utf-8")
        style_scss = (
            STARTER_ROOT
            / "src/scss/layouts/footer/_footer-style.scss"
        ).read_text(encoding="utf-8")
        compiled_css = (
            STARTER_ROOT / "dist/css/main.css"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "| `.footer__top` | brand と nav の上段枠 |",
            docs,
        )
        self.assertIn(
            "footer内CTAが必要な時だけ `.footer__cta` を使う",
            docs,
        )

        canonical_match = re.search(
            r"## Standard footer.*?```html\s+(.*?)```",
            docs,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(canonical_match)
        assert canonical_match is not None
        canonical = parse_document(canonical_match.group(1))
        canonical_footers = elements_with_class(
            canonical,
            "site-footer--standard",
        )
        self.assertEqual(1, len(canonical_footers))
        canonical_tops = elements_with_class(
            canonical_footers[0],
            "footer__top",
        )
        self.assertEqual(1, len(canonical_tops))
        self.assertEqual(
            ["footer__brand", "footer__nav"],
            [
                "footer__brand"
                if "footer__brand" in child.classes
                else "footer__nav"
                if "footer__nav" in child.classes
                else component_name(child)
                for child in element_children(canonical_tops[0])
            ],
        )

        top_selector = (
            ".site-footer.site-footer--standard .footer__top"
        )
        for source in (structure_scss, compiled_css):
            source_without_comments = re.sub(
                r"/\*.*?\*/",
                "",
                source,
                flags=re.DOTALL,
            )
            top_bodies = css_rule_bodies(
                source_without_comments,
                top_selector,
            )
            self.assertTrue(
                has_declaration(top_bodies, "display", "grid")
            )
            self.assertTrue(
                has_declaration(
                    top_bodies,
                    "grid-template-columns",
                    "minmax(0, 1fr) auto",
                )
            )
            for selector in (
                ".site-footer.site-footer--standard .footer__brand",
                ".site-footer.site-footer--standard .footer__cta",
                ".site-footer.site-footer--standard .footer__nav",
                ".site-footer.site-footer--standard .footer__links",
                ".site-footer.site-footer--standard .footer__copy",
            ):
                self.assertTrue(
                    css_rule_bodies(
                        source_without_comments,
                        selector,
                    ),
                    selector,
                )

        style_scss_without_comments = re.sub(
            r"/\*.*?\*/",
            "",
            style_scss,
            flags=re.DOTALL,
        )
        compiled_css_without_comments = re.sub(
            r"/\*.*?\*/",
            "",
            compiled_css,
            flags=re.DOTALL,
        )
        self.assertTrue(
            css_rule_bodies(
                style_scss_without_comments,
                ".site-footer.site-footer--standard .footer__copy",
            )
        )
        self.assertTrue(
            css_rule_bodies(
                compiled_css_without_comments,
                ".site-footer.site-footer--standard .footer__copy",
            )
        )

        starter_contract = "\n".join(
            (docs, structure_scss, style_scss, compiled_css)
        )
        for class_name in FORBIDDEN_FOOTER_CLASSES:
            self.assertIsNone(
                re.search(
                    rf"(?<![\w-]){re.escape(class_name)}(?![\w-])",
                    starter_contract,
                ),
                class_name,
            )

    def test_generated_templates_preserve_footer_and_prior_contracts(
        self,
    ) -> None:
        expected_actions = expectations_by_path()

        with tempfile.TemporaryDirectory(
            prefix="pg-html-007-"
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
                project_name = f"{template_name} Footer Contract"
                starter_dist = STARTER_ROOT / "dist"

                with patch.object(
                    script,
                    "resolve_exiga_dist",
                    return_value=starter_dist,
                ):
                    output_dir = script.create_project(
                        base_dir=base_dir,
                        template_name=template_name,
                        project_name=project_name,
                        force=True,
                    )

                generated_documents: dict[str, str] = {}
                for html_path in sorted(output_dir.rglob("*.html")):
                    relative_path = html_path.relative_to(
                        output_dir
                    ).as_posix()
                    source_path = f"{template_name}/{relative_path}"
                    text = html_path.read_text(encoding="utf-8")
                    generated_documents[source_path] = text
                    self.assertEqual(
                        [],
                        footer_contract_errors(
                            text,
                            FOOTER_EXPECTATIONS[source_path],
                            project_name=project_name,
                            generated_date=date.today().isoformat(),
                        ),
                        source_path,
                    )
                    self.assertEqual(
                        [],
                        document_contract_errors(
                            source_path,
                            text,
                            project_name=project_name,
                        ),
                        source_path,
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
                        form_accessibility_errors(
                            text,
                            source_name=source_path,
                        ),
                        source_path,
                    )
                    self.assertTrue(
                        {
                            f"t-{template_name}",
                            page_class_for(source_path),
                        }.issubset(body_classes(text))
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

                self.assertEqual(
                    (),
                    filesystem_safety.find_project_transaction_artifacts(
                        output_dir
                    ),
                )

        self.assertFalse(temp_path.exists())

    def test_wordpress_conversion_extracts_footer_once(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="pg-html-007-wp-"
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

            project_name = "Footer WordPress Contract"
            with patch.object(
                script,
                "resolve_exiga_dist",
                return_value=STARTER_ROOT / "dist",
            ):
                output_dir = script.create_project(
                    base_dir=base_dir,
                    template_name="website",
                    project_name=project_name,
                    force=True,
                )

            project_dir, generated_files = (
                convert_to_wp.convert_project(
                    base_dir=base_dir,
                    project_name=output_dir.name,
                    template_name="website",
                )
            )
            footer_php = (project_dir / "footer.php").read_text(
                encoding="utf-8"
            )
            self.assertEqual(
                1,
                len(re.findall(r"<footer\b", footer_php, re.I)),
            )
            self.assertEqual(
                1,
                len(re.findall(r"</footer>", footer_php, re.I)),
            )

            sanitized_footer = re.sub(
                r"<\?php.*?\?>",
                "",
                footer_php,
                flags=re.DOTALL,
            )
            wp_expectation = replace(
                FOOTER_EXPECTATIONS["website/index.html"],
                navigation=tuple(
                    ("", label)
                    for _, label in WEBSITE_NAVIGATION
                ),
            )
            self.assertEqual(
                [],
                footer_contract_errors(
                    sanitized_footer,
                    wp_expectation,
                    project_name=project_name,
                    generated_date=date.today().isoformat(),
                ),
            )
            self.assertIn("<?php wp_footer(); ?>", footer_php)

            for php_name in (
                "front-page.php",
                "page-about.php",
                "page-contact.php",
                "page-service.php",
            ):
                page_php = (project_dir / php_name).read_text(
                    encoding="utf-8"
                )
                self.assertNotRegex(page_php, r"<footer\b")
                self.assertEqual(1, page_php.count("<?php get_footer(); ?>"))

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
                filesystem_safety.find_project_transaction_artifacts(
                    project_dir
                ),
            )


if __name__ == "__main__":
    unittest.main()
