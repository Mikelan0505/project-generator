from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import script

try:
    from .test_template_accordion import (
        accordion_contract_errors,
        element_children,
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
    )
    from .test_template_references import (
        form_accessibility_errors,
    )
except ImportError:
    from test_template_accordion import (
        accordion_contract_errors,
        element_children,
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
    )
    from test_template_references import (
        form_accessibility_errors,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
STARTER_ROOT = REPOSITORY_ROOT.parent / "sass-starter-exiga"
DEPRECATED_FLEX_CLASSES = {
    "u-flex",
    "u-flex-sp-col",
    "u-flex-wrap",
}
ACTION_OWNER_CLASSES = {
    "c-hero__actions",
    "c-cta-block__actions",
}
INTERACTIVE_TAGS = {
    "a",
    "button",
    "input",
    "select",
    "summary",
    "textarea",
}

ActionSnapshot = tuple[
    str,
    str | None,
    str,
    tuple[str, ...],
]


@dataclass(frozen=True)
class ExpectedGroup:
    template_path: str
    section_label: str
    owner_class: str
    actions: tuple[ActionSnapshot, ...]
    changed: bool = True


def link(
    href: str,
    text: str,
    modifier: str | None = None,
) -> ActionSnapshot:
    modifiers = (modifier,) if modifier else ()
    return ("a", href, text, modifiers)


EXPECTED_GROUPS = (
    ExpectedGroup(
        "website/index.html",
        "hero-title",
        "c-hero__actions",
        (
            link(
                "./contact.html",
                "お問い合わせ導線を確認",
                "c-button--cta",
            ),
            link(
                "./service.html",
                "サービスページを見る",
                "c-button--outline-secondary",
            ),
        ),
        changed=False,
    ),
    ExpectedGroup(
        "website/index.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "./contact.html",
                "お問い合わせページへ",
                "c-button--cta",
            ),
            link(
                "./about.html",
                "会社案内を見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "website/about.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "./contact.html",
                "お問い合わせへ",
                "c-button--cta",
            ),
            link(
                "./service.html",
                "サービスを見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "website/service.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "./contact.html",
                "相談する",
                "c-button--cta",
            ),
            link(
                "./about.html",
                "会社情報を見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "shop/index.html",
        "hero-title",
        "c-hero__actions",
        (
            link(
                "./products.html",
                "商品一覧を見る",
                "c-button--cta",
            ),
            link(
                "./contact.html",
                "取り置き・問い合わせへ",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "shop/index.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "./contact.html",
                "問い合わせる",
                "c-button--cta",
            ),
            link(
                "./products.html",
                "商品一覧を見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "shop/about.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "./contact.html",
                "問い合わせる",
                "c-button--cta",
            ),
            link(
                "./products.html",
                "商品一覧を見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "shop/products.html",
        "category-nav-title",
        "c-cta-block__actions",
        (
            link("#category-standard", "定番商品"),
            link("#category-seasonal", "季節限定"),
            link("#category-gift", "ギフト向け"),
        ),
    ),
    ExpectedGroup(
        "shop/products.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "./contact.html",
                "商品について問い合わせる",
                "c-button--cta",
            ),
            link(
                "./about.html",
                "店舗情報を見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "lp/index.html",
        "hero-title",
        "c-hero__actions",
        (
            link(
                "#cta",
                "お問い合わせ導線を確認",
                "c-button--cta",
            ),
            link(
                "#offer",
                "サービスページを見る",
                "c-button--outline-secondary",
            ),
        ),
    ),
    ExpectedGroup(
        "lp/index.html",
        "cta-title",
        "c-cta-block__actions",
        (
            link(
                "mailto:info@example.com",
                "お問い合わせする",
                "c-button--cta",
            ),
            link(
                "#top",
                "ページ上部へ戻る",
                "c-button--outline-secondary",
            ),
        ),
    ),
)


def expectations_by_path() -> dict[
    str,
    tuple[ExpectedGroup, ...],
]:
    return {
        template_path: tuple(
            group
            for group in EXPECTED_GROUPS
            if group.template_path == template_path
        )
        for template_path in {
            group.template_path
            for group in EXPECTED_GROUPS
        }
    }


def action_snapshot(owner) -> tuple[
    ActionSnapshot,
    ...,
]:
    actions = [
        child
        for child in element_children(owner)
        if child.tag in {"a", "button"}
    ]
    return tuple(
        (
            action.tag,
            action.attrs.get("href"),
            visible_text(action),
            tuple(
                sorted(
                    class_name
                    for class_name in action.classes
                    if class_name.startswith("c-button--")
                )
            ),
        )
        for action in actions
    )


def cta_contract_errors(
    text: str,
    expected_groups: tuple[ExpectedGroup, ...],
) -> list[str]:
    document = parse_document(text)
    all_elements = list(walk(document))
    errors = [
        f"deprecated-class:{class_name}"
        for class_name in sorted(
            DEPRECATED_FLEX_CLASSES
            & {
                class_name
                for element in all_elements
                for class_name in element.classes
            }
        )
    ]
    all_owners = [
        element
        for element in all_elements
        if element.classes & ACTION_OWNER_CLASSES
    ]

    if len(all_owners) != len(expected_groups):
        errors.append(
            "action-owner-count:"
            f"expected={len(expected_groups)} "
            f"actual={len(all_owners)}"
        )

    for group in expected_groups:
        sections = [
            element
            for element in all_elements
            if (
                element.tag == "section"
                and element.attrs.get("aria-labelledby")
                == group.section_label
            )
        ]

        if len(sections) != 1:
            errors.append(
                f"{group.section_label}:section-count:"
                f"{len(sections)}"
            )
            continue

        owners = [
            element
            for element in walk(sections[0])
            if element.classes & ACTION_OWNER_CLASSES
        ]

        if not owners:
            errors.append(
                f"{group.section_label}:missing layout owner"
            )
            continue

        if len(owners) != 1:
            errors.append(
                f"{group.section_label}:double owner"
            )

        owner = owners[0]
        owned_classes = owner.classes & ACTION_OWNER_CLASSES

        if owned_classes != {group.owner_class}:
            errors.append(
                f"{group.section_label}:wrong owner:"
                f"expected={group.owner_class} "
                f"actual={','.join(sorted(owned_classes))}"
            )

        if any(
            descendant.classes & ACTION_OWNER_CLASSES
            for descendant in walk(owner)
        ):
            errors.append(
                f"{group.section_label}:nested owner"
            )

        actions = [
            child
            for child in element_children(owner)
            if child.tag in {"a", "button"}
        ]

        if any(
            "c-button" not in action.classes
            for action in actions
        ):
            errors.append(
                f"{group.section_label}:action missing c-button"
            )

        actual_snapshot = action_snapshot(owner)

        if len(actual_snapshot) != len(group.actions):
            errors.append(
                f"{group.section_label}:action-count:"
                f"expected={len(group.actions)} "
                f"actual={len(actual_snapshot)}"
            )

        if actual_snapshot != group.actions:
            errors.append(
                f"{group.section_label}:action snapshot mismatch"
            )

    return errors


def css_rule_bodies(
    text: str,
    selector: str,
) -> list[str]:
    bodies: list[str] = []

    for match in re.finditer(
        r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}",
        text,
    ):
        selectors = {
            candidate.strip()
            for candidate in match.group("selectors").split(",")
        }

        if selector in selectors:
            bodies.append(match.group("body"))

    return bodies


def has_declaration(
    bodies: list[str],
    property_name: str,
    value: str,
) -> bool:
    pattern = re.compile(
        rf"{re.escape(property_name)}\s*:\s*"
        rf"{re.escape(value)}\s*;"
    )
    return any(pattern.search(body) for body in bodies)


def body_classes(text: str) -> set[str]:
    document = parse_document(text)
    bodies = [
        element
        for element in walk(document)
        if element.tag == "body"
    ]
    return bodies[0].classes if len(bodies) == 1 else set()


def generated_regression_errors(
    template_name: str,
    output_dir: Path,
) -> list[str]:
    errors: list[str] = []

    if template_name == "website":
        document = parse_document(
            (output_dir / "index.html").read_text(
                encoding="utf-8"
            )
        )
        overlays = elements_with_class(
            document,
            "c-hero__overlay",
        )

        if any(
            element.tag in INTERACTIVE_TAGS
            or "tabindex" in element.attrs
            for overlay in overlays
            for element in walk(overlay)
        ):
            errors.append("website:interactive hero overlay")

    if template_name == "shop":
        document = parse_document(
            (output_dir / "products.html").read_text(
                encoding="utf-8"
            )
        )

        if len(
            elements_with_class(document, "c-product-grid")
        ) != 3:
            errors.append("shop:product-grid-count")

        if len(
            elements_with_class(document, "c-product-card")
        ) != 21:
            errors.append("shop:product-card-count")

    if template_name == "lp":
        errors.extend(
            f"lp:{error}"
            for error in accordion_contract_errors(
                (output_dir / "index.html").read_text(
                    encoding="utf-8"
                ),
                expected_item_count=3,
            )
        )

    return errors


FIXTURE_ACTIONS = (
    link("/contact/", "Contact", "c-button--cta"),
    link(
        "/about/",
        "About",
        "c-button--outline-secondary",
    ),
)
HERO_FIXTURE_GROUP = ExpectedGroup(
    "fixture.html",
    "hero-title",
    "c-hero__actions",
    FIXTURE_ACTIONS,
)
CTA_FIXTURE_GROUP = ExpectedGroup(
    "fixture.html",
    "cta-title",
    "c-cta-block__actions",
    FIXTURE_ACTIONS,
)
HERO_FIXTURE = """
<section aria-labelledby="hero-title">
  <h1 id="hero-title">Hero</h1>
  <div class="c-hero__actions">
    <a class="c-button c-button--cta" href="/contact/">Contact</a>
    <a class="c-button c-button--outline-secondary" href="/about/">About</a>
  </div>
</section>
"""
CTA_FIXTURE = HERO_FIXTURE.replace(
    "hero-title",
    "cta-title",
).replace(
    "c-hero__actions",
    "c-cta-block__actions",
)


class TemplateCtaTests(unittest.TestCase):
    def test_templates_preserve_canonical_action_groups(
        self,
    ) -> None:
        by_path = expectations_by_path()
        self.assertEqual(
            10,
            sum(group.changed for group in EXPECTED_GROUPS),
        )

        for template_path, groups in sorted(
            by_path.items()
        ):
            with self.subTest(template_path=template_path):
                text = (
                    TEMPLATES_ROOT / template_path
                ).read_text(encoding="utf-8")
                self.assertEqual(
                    [],
                    cta_contract_errors(text, groups),
                )

    def test_deprecated_flex_classes_are_absent_from_templates(
        self,
    ) -> None:
        errors: list[str] = []

        for path in sorted(
            TEMPLATES_ROOT.rglob("*.html")
        ):
            document = parse_document(
                path.read_text(encoding="utf-8")
            )
            deprecated = sorted(
                DEPRECATED_FLEX_CLASSES
                & {
                    class_name
                    for element in walk(document)
                    for class_name in element.classes
                }
            )

            if deprecated:
                errors.append(
                    f"{path.relative_to(TEMPLATES_ROOT)}: "
                    f"{', '.join(deprecated)}"
                )

        self.assertEqual([], errors, "\n".join(errors))

    def test_cta_validator_rejects_invalid_contracts(
        self,
    ) -> None:
        invalid_cases = {
            "u-flex": (
                HERO_FIXTURE.replace(
                    "c-hero__actions",
                    "c-hero__actions u-flex",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "deprecated-class:u-flex",
            ),
            "u-flex-sp-col": (
                HERO_FIXTURE.replace(
                    "c-hero__actions",
                    "c-hero__actions u-flex-sp-col",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "deprecated-class:u-flex-sp-col",
            ),
            "u-flex-wrap": (
                HERO_FIXTURE.replace(
                    "c-hero__actions",
                    "c-hero__actions u-flex-wrap",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "deprecated-class:u-flex-wrap",
            ),
            "missing-owner": (
                HERO_FIXTURE.replace(
                    "c-hero__actions",
                    "actions",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "missing layout owner",
            ),
            "hero-wrong-owner": (
                HERO_FIXTURE.replace(
                    "c-hero__actions",
                    "c-cta-block__actions",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "wrong owner",
            ),
            "cta-wrong-owner": (
                CTA_FIXTURE.replace(
                    "c-cta-block__actions",
                    "c-hero__actions",
                    1,
                ),
                (CTA_FIXTURE_GROUP,),
                "wrong owner",
            ),
            "action-removed": (
                HERO_FIXTURE.replace(
                    '    <a class="c-button '
                    'c-button--outline-secondary" '
                    'href="/about/">About</a>\n',
                    "",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "action-count",
            ),
            "href-changed": (
                HERO_FIXTURE.replace(
                    'href="/about/"',
                    'href="/service/"',
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "action snapshot mismatch",
            ),
            "text-changed": (
                HERO_FIXTURE.replace(
                    ">About</a>",
                    ">Service</a>",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "action snapshot mismatch",
            ),
            "order-changed": (
                HERO_FIXTURE.replace(
                    FIXTURE_ACTIONS[0][2],
                    "Temporary",
                    1,
                ).replace(
                    FIXTURE_ACTIONS[1][2],
                    FIXTURE_ACTIONS[0][2],
                    1,
                ).replace(
                    "Temporary",
                    FIXTURE_ACTIONS[1][2],
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "action snapshot mismatch",
            ),
            "nested-owner": (
                HERO_FIXTURE.replace(
                    '<div class="c-hero__actions">',
                    '<div class="c-hero__actions">'
                    '<div class="c-hero__actions">',
                    1,
                ).replace(
                    "  </div>\n</section>",
                    "  </div></div>\n</section>",
                    1,
                ),
                (HERO_FIXTURE_GROUP,),
                "nested owner",
            ),
        }

        for name, (
            markup,
            expected_groups,
            expected_error,
        ) in invalid_cases.items():
            with self.subTest(name=name):
                errors = cta_contract_errors(
                    markup,
                    expected_groups,
                )
                self.assertTrue(
                    any(
                        expected_error in error
                        for error in errors
                    ),
                    errors,
                )

    def test_starter_owns_action_layout_contracts(
        self,
    ) -> None:
        docs = (
            STARTER_ROOT / "docs/components/cta.md"
        ).read_text(encoding="utf-8")
        cta_scss = (
            STARTER_ROOT
            / "src/scss/components/cta/_cta-block.scss"
        ).read_text(encoding="utf-8")
        hero_scss = (
            STARTER_ROOT
            / "src/scss/components/hero/_hero.scss"
        ).read_text(encoding="utf-8")
        compiled_css = (
            STARTER_ROOT / "dist/css/main.css"
        ).read_text(encoding="utf-8")

        self.assertIn("## Actions-only structure", docs)
        self.assertIn(
            '<div class="c-cta-block__actions">',
            docs,
        )

        cta_desktop, cta_mobile = cta_scss.split(
            "@include u.mq-down(md)",
            maxsplit=1,
        )
        hero_desktop, hero_mobile = hero_scss.split(
            "@include u.mq-down(md)",
            maxsplit=1,
        )
        cta_desktop_bodies = css_rule_bodies(
            cta_desktop,
            ".c-cta-block__actions",
        )
        cta_mobile_bodies = css_rule_bodies(
            cta_mobile,
            ".c-cta-block__actions",
        )
        hero_desktop_bodies = css_rule_bodies(
            hero_desktop,
            ".c-hero__actions",
        )
        hero_mobile_button_bodies = css_rule_bodies(
            hero_mobile,
            ".c-hero__actions .c-button",
        )

        for bodies in (
            cta_desktop_bodies,
            hero_desktop_bodies,
        ):
            self.assertTrue(
                has_declaration(bodies, "display", "flex")
            )
            self.assertTrue(
                has_declaration(
                    bodies,
                    "flex-wrap",
                    "wrap",
                )
            )
            self.assertTrue(
                has_declaration(
                    bodies,
                    "gap",
                    "var(--dist-16)",
                )
            )

        self.assertTrue(
            has_declaration(
                cta_mobile_bodies,
                "display",
                "grid",
            )
        )
        self.assertTrue(
            has_declaration(
                cta_mobile_bodies,
                "grid-template-columns",
                "1fr",
            )
        )
        self.assertTrue(
            has_declaration(
                hero_mobile_button_bodies,
                "inline-size",
                "min(100%, 17.5rem)",
            )
        )

        compiled_cta_bodies = css_rule_bodies(
            compiled_css,
            ".c-cta-block__actions",
        )
        compiled_cta_button_bodies = css_rule_bodies(
            compiled_css,
            ".c-cta-block__actions .c-button",
        )
        compiled_hero_bodies = css_rule_bodies(
            compiled_css,
            ".c-hero__actions",
        )
        compiled_hero_button_bodies = css_rule_bodies(
            compiled_css,
            ".c-hero__actions .c-button",
        )

        self.assertTrue(
            has_declaration(
                compiled_cta_bodies,
                "flex-wrap",
                "wrap",
            )
        )
        self.assertTrue(
            has_declaration(
                compiled_cta_bodies,
                "grid-template-columns",
                "1fr",
            )
        )
        self.assertTrue(
            has_declaration(
                compiled_cta_button_bodies,
                "inline-size",
                "13.75rem",
            )
        )
        self.assertTrue(
            has_declaration(
                compiled_hero_bodies,
                "flex-wrap",
                "wrap",
            )
        )
        self.assertTrue(
            has_declaration(
                compiled_hero_button_bodies,
                "inline-size",
                "min(100%, 17.5rem)",
            )
        )

    def test_generated_templates_preserve_action_contracts(
        self,
    ) -> None:
        by_path = expectations_by_path()

        with tempfile.TemporaryDirectory(
            prefix="pg-html-004-"
        ) as temp:
            temp_path = Path(temp)

            for template_name in (
                "website",
                "shop",
                "lp",
            ):
                base_dir = (
                    temp_path
                    / template_name
                    / "project-generator"
                )
                shutil.copytree(
                    TEMPLATES_ROOT / template_name,
                    base_dir
                    / "templates"
                    / template_name,
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
                            f"{template_name} CTA Contract"
                        ),
                        force=True,
                    )

                for html_path in sorted(
                    output_dir.rglob("*.html")
                ):
                    relative_template_path = (
                        f"{template_name}/"
                        f"{html_path.relative_to(output_dir).as_posix()}"
                    )
                    text = html_path.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(
                        [],
                        cta_contract_errors(
                            text,
                            by_path.get(
                                relative_template_path,
                                (),
                            ),
                        ),
                        relative_template_path,
                    )
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
                            source_name=(
                                relative_template_path
                            ),
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

                for relative_path in (
                    Path("css/main.css"),
                    Path("js/core/app.js"),
                ):
                    self.assertEqual(
                        (
                            starter_dist / relative_path
                        ).read_bytes(),
                        (
                            output_dir
                            / "dist"
                            / relative_path
                        ).read_bytes(),
                    )

        self.assertFalse(temp_path.exists())


if __name__ == "__main__":
    unittest.main()
