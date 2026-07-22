from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
import unittest
import re

import script


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
STARTER_ROOT = REPOSITORY_ROOT.parent / "sass-starter-exiga"

GENERATED_DIST_REFERENCES = {
    "dist/css/main.css",
    "dist/js/core/app.js",
}
NON_LABEL_REQUIRED_INPUT_TYPES = {
    "button",
    "hidden",
    "image",
    "reset",
    "submit",
}
HERO_OVERLAY_INTERACTIVE_TAGS = {
    "a",
    "button",
    "input",
    "select",
    "summary",
    "textarea",
}
HTML_VOID_ELEMENTS = {
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
}
DEPRECATED_PRODUCT_CLASSES = {
    "l-grid--cards-4",
    "text-price",
    "text-price__prefix",
}
EXPECTED_SHOP_CATEGORY_IDS = [
    "category-standard",
    "category-seasonal",
    "category-gift",
]
EXPECTED_SHOP_CATEGORY_HREFS = [
    "#category-standard",
    "#category-seasonal",
    "#category-gift",
]
EXPECTED_SHOP_GRID_CARD_COUNTS = [9, 6, 6]
EXPECTED_SHOP_PRODUCTS = [
    ("スタンダードブレンド", "税込 1,080円"),
    ("焼き菓子アソート", "税込 1,620円"),
    ("オリジナル雑貨", "税込 880円"),
    ("定番クッキー缶", "税込 2,480円"),
    ("デイリーパック", "税込 756円"),
    ("店主おすすめセット", "税込 1,980円"),
    ("ミニギフトボックス", "税込 1,296円"),
    ("シンプルセレクション", "税込 1,430円"),
    ("リピート定番商品", "税込 972円"),
    ("季節の詰め合わせ", "税込 2,160円"),
    ("限定ロースト", "税込 1,350円"),
    ("季節ラッピング商品", "税込 2,970円"),
    ("季節の冷菓セット", "税込 1,890円"),
    ("濃厚シーズンセレクト", "税込 1,480円"),
    ("イベント限定ボックス", "税込 3,240円"),
    ("手土産セット", "税込 2,430円"),
    ("ラッピング対応商品", "税込 3,300円"),
    ("ちいさな贈り物", "税込 1,100円"),
    ("きちんと贈れる定番箱", "税込 3,780円"),
    ("気軽な贈りものセット", "税込 1,650円"),
    ("季節の贈答ボックス", "税込 2,860円"),
]


class TemplateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.classes: list[str] = []
        self.references: list[
            tuple[int, str, str, str]
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")

        if element_id:
            self.ids.append(element_id)

        class_value = attributes.get("class")

        if class_value:
            self.classes.extend(
                class_value.split()
            )

        line_number, _ = self.getpos()

        for attribute_name in ("href", "src"):
            value = attributes.get(attribute_name)

            if value is not None:
                self.references.append(
                    (
                        line_number,
                        tag,
                        attribute_name,
                        value,
                    )
                )


def parse_template(path: Path) -> TemplateParser:
    parser = TemplateParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


class HeroContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[
            tuple[str, frozenset[str], int | None]
        ] = []
        self.overlay_interactive_elements: list[
            tuple[int, str]
        ] = []
        self.hero_count = 0
        self.hero_content_count = 0
        self.hero_actions_count = 0
        self.hero_classes: set[str] = set()
        self.hero_action_links: list[
            dict[str, object]
        ] = []

    def has_ancestor_class(
        self,
        class_name: str,
    ) -> bool:
        return any(
            class_name in classes
            for _, classes, _ in self.stack
        )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_element_start(
            tag,
            attrs,
            push=tag.lower() not in HTML_VOID_ELEMENTS,
        )

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_element_start(
            tag,
            attrs,
            push=False,
        )

    def handle_element_start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        push: bool,
    ) -> None:
        normalized_tag = tag.lower()
        attributes = dict(attrs)
        classes = frozenset(
            (attributes.get("class") or "").split()
        )
        line_number, _ = self.getpos()
        inside_overlay = self.has_ancestor_class(
            "c-hero__overlay"
        )
        inside_hero = self.has_ancestor_class(
            "c-hero"
        )
        inside_content = self.has_ancestor_class(
            "c-hero__content"
        )
        inside_actions = self.has_ancestor_class(
            "c-hero__actions"
        )

        if (
            inside_overlay
            or "c-hero__overlay" in classes
        ) and (
            normalized_tag
            in HERO_OVERLAY_INTERACTIVE_TAGS
            or "tabindex" in attributes
        ):
            self.overlay_interactive_elements.append(
                (line_number, normalized_tag)
            )

        if "c-hero" in classes:
            self.hero_count += 1

        if inside_hero or "c-hero" in classes:
            self.hero_classes.update(classes)

        if (
            "c-hero__content" in classes
            and inside_hero
            and not inside_overlay
        ):
            self.hero_content_count += 1

        if (
            "c-hero__actions" in classes
            and inside_hero
            and inside_content
            and not inside_overlay
        ):
            self.hero_actions_count += 1

        action_link_index: int | None = None

        if (
            normalized_tag == "a"
            and inside_hero
            and inside_content
            and inside_actions
            and not inside_overlay
        ):
            action_link_index = len(
                self.hero_action_links
            )
            self.hero_action_links.append(
                {
                    "href": attributes.get("href"),
                    "text": "",
                }
            )

        if push:
            self.stack.append(
                (
                    normalized_tag,
                    classes,
                    action_link_index,
                )
            )

    def handle_data(self, data: str) -> None:
        for _, _, link_index in reversed(
            self.stack
        ):
            if link_index is None:
                continue

            current_text = self.hero_action_links[
                link_index
            ]["text"]
            assert isinstance(current_text, str)
            self.hero_action_links[link_index][
                "text"
            ] = current_text + data
            return

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()

        for index in range(
            len(self.stack) - 1,
            -1,
            -1,
        ):
            if self.stack[index][0] != normalized_tag:
                continue

            del self.stack[index:]
            return


def parse_hero_contract_text(
    text: str,
) -> HeroContractParser:
    parser = HeroContractParser()
    parser.feed(text)
    parser.close()
    return parser


def parse_hero_contract(
    path: Path,
) -> HeroContractParser:
    return parse_hero_contract_text(
        path.read_text(encoding="utf-8")
    )


class ProductListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[
            tuple[str, int | None, int | None, str | None]
        ] = []
        self.grid_classes: list[frozenset[str]] = []
        self.grid_card_indexes: list[list[int]] = []
        self.card_tags: list[str] = []
        self.card_titles: list[str] = []
        self.card_prices: list[str] = []
        self.card_title_counts: list[int] = []
        self.card_price_counts: list[int] = []
        self.category_ids: list[str] = []
        self.category_hrefs: list[str] = []
        self.body_classes: set[str] = set()

    def current_grid_index(self) -> int | None:
        return next(
            (
                grid_index
                for _, grid_index, _, _ in reversed(
                    self.stack
                )
                if grid_index is not None
            ),
            None,
        )

    def current_card_index(self) -> int | None:
        return next(
            (
                card_index
                for _, _, card_index, _ in reversed(
                    self.stack
                )
                if card_index is not None
            ),
            None,
        )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_element_start(
            tag,
            attrs,
            push=tag.lower() not in HTML_VOID_ELEMENTS,
        )

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_element_start(
            tag,
            attrs,
            push=False,
        )

    def handle_element_start(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        push: bool,
    ) -> None:
        normalized_tag = tag.lower()
        attributes = dict(attrs)
        classes = frozenset(
            (attributes.get("class") or "").split()
        )
        grid_index = self.current_grid_index()
        card_index = self.current_card_index()
        capture: str | None = None

        if normalized_tag == "body":
            self.body_classes.update(classes)

        element_id = attributes.get("id")

        if (
            normalized_tag == "section"
            and isinstance(element_id, str)
            and element_id.startswith("category-")
        ):
            self.category_ids.append(element_id)

        href = attributes.get("href")

        if (
            normalized_tag == "a"
            and isinstance(href, str)
            and href.startswith("#category-")
        ):
            self.category_hrefs.append(href)

        if "c-product-grid" in classes:
            grid_index = len(self.grid_classes)
            self.grid_classes.append(classes)
            self.grid_card_indexes.append([])

        if "c-product-card" in classes:
            card_index = len(self.card_titles)
            self.card_tags.append(normalized_tag)
            self.card_titles.append("")
            self.card_prices.append("")
            self.card_title_counts.append(0)
            self.card_price_counts.append(0)

            if grid_index is not None:
                self.grid_card_indexes[
                    grid_index
                ].append(card_index)

        if (
            "c-product-card__title" in classes
            and card_index is not None
        ):
            self.card_title_counts[card_index] += 1
            capture = "title"

        if (
            "c-product-card__price" in classes
            and card_index is not None
        ):
            self.card_price_counts[card_index] += 1
            capture = "price"

        if push:
            self.stack.append(
                (
                    normalized_tag,
                    grid_index,
                    card_index,
                    capture,
                )
            )

    def handle_data(self, data: str) -> None:
        for _, _, card_index, capture in reversed(
            self.stack
        ):
            if card_index is None or capture is None:
                continue

            target = (
                self.card_titles
                if capture == "title"
                else self.card_prices
            )
            target[card_index] += data
            return

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()

        for index in range(
            len(self.stack) - 1,
            -1,
            -1,
        ):
            if self.stack[index][0] != normalized_tag:
                continue

            del self.stack[index:]
            return


def parse_product_listing_text(
    text: str,
) -> ProductListingParser:
    parser = ProductListingParser()
    parser.feed(text)
    parser.close()
    return parser


def parse_product_listing(
    path: Path,
) -> ProductListingParser:
    return parse_product_listing_text(
        path.read_text(encoding="utf-8")
    )


def normalized_text(text: str) -> str:
    return " ".join(text.split())


def product_listing_contract_errors(
    text: str,
    *,
    expected_grid_count: int,
    expected_product_count: int,
) -> list[str]:
    template_parser = TemplateParser()
    template_parser.feed(text)
    template_parser.close()
    parser = parse_product_listing_text(text)
    errors = [
        f"deprecated-class:{class_name}"
        for class_name in sorted(
            DEPRECATED_PRODUCT_CLASSES
            & set(template_parser.classes)
        )
    ]

    if len(parser.grid_classes) != expected_grid_count:
        errors.append(
            "product-grid-count:"
            f"expected={expected_grid_count} "
            f"actual={len(parser.grid_classes)}"
        )

    for index, classes in enumerate(
        parser.grid_classes,
        start=1,
    ):
        if "c-product-grid--cols-4" not in classes:
            errors.append(
                f"product-grid-{index}:"
                "missing c-product-grid--cols-4"
            )

    if len(parser.card_titles) != expected_product_count:
        errors.append(
            "product-card-count:"
            f"expected={expected_product_count} "
            f"actual={len(parser.card_titles)}"
        )

    for index, (
        tag,
        title,
        price,
        title_count,
        price_count,
    ) in enumerate(
        zip(
            parser.card_tags,
            parser.card_titles,
            parser.card_prices,
            parser.card_title_counts,
            parser.card_price_counts,
            strict=True,
        ),
        start=1,
    ):
        if tag != "article":
            errors.append(
                f"product-card-{index}:root is not article"
            )

        if title_count != 1 or not normalized_text(title):
            errors.append(
                f"product-card-{index}:missing title"
            )

        if price_count != 1 or not normalized_text(price):
            errors.append(
                f"product-card-{index}:missing price"
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
            for candidate in match.group(
                "selectors"
            ).split(",")
        }

        if selector in selectors:
            bodies.append(match.group("body"))

    return bodies


class FormAccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[
            dict[str, object]
        ] = []
        self.labels: list[
            dict[str, object]
        ] = []
        self.open_labels: list[
            dict[str, object]
        ] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        line_number, _ = self.getpos()
        normalized_tag = tag.lower()

        if normalized_tag == "label":
            label = {
                "line": line_number,
                "for": attributes.get("for"),
                "controls": [],
            }
            self.labels.append(label)
            self.open_labels.append(label)
            return

        if not self.is_labelable_control(
            normalized_tag,
            attributes,
        ):
            return

        control_index = len(self.controls)
        self.controls.append(
            {
                "line": line_number,
                "tag": normalized_tag,
                "id": attributes.get("id"),
                "aria-label": (
                    attributes.get("aria-label")
                ),
                "aria-labelledby": (
                    attributes.get(
                        "aria-labelledby"
                    )
                ),
            }
        )

        for label in self.open_labels:
            controls = label["controls"]
            assert isinstance(controls, list)
            controls.append(control_index)

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if (
            tag.lower() == "label"
            and self.open_labels
        ):
            self.open_labels.pop()

    @staticmethod
    def is_labelable_control(
        tag: str,
        attributes: dict[str, str | None],
    ) -> bool:
        if tag in {"select", "textarea"}:
            return True

        if tag != "input":
            return False

        input_type = (
            attributes.get("type")
            or "text"
        ).lower()

        return (
            input_type
            not in NON_LABEL_REQUIRED_INPUT_TYPES
        )


def form_accessibility_errors(
    text: str,
    *,
    source_name: str,
) -> list[str]:
    parser = FormAccessibilityParser()
    parser.feed(text)
    parser.close()

    errors: list[str] = []
    controls_by_id: dict[str, int] = {}

    for index, control in enumerate(
        parser.controls
    ):
        control_id = control["id"]

        if not isinstance(control_id, str):
            continue

        if control_id in controls_by_id:
            errors.append(
                f"{source_name}: control idが"
                f"重複しています: {control_id}"
            )
            continue

        controls_by_id[control_id] = index

    explicit_targets: list[str] = []
    implicit_control_indexes: set[int] = set()

    for label in parser.labels:
        line_number = label["line"]
        target = label["for"]
        nested_controls = label["controls"]

        assert isinstance(line_number, int)
        assert isinstance(nested_controls, list)

        if isinstance(target, str):
            explicit_targets.append(target)

            if target not in controls_by_id:
                errors.append(
                    f"{source_name}:{line_number}: "
                    f"label[for={target}]の対象"
                    "controlがありません。"
                )

            continue

        if len(nested_controls) != 1:
            errors.append(
                f"{source_name}:{line_number}: "
                "内包labelはlabelable controlを"
                "1つだけ含む必要があります。"
            )
            continue

        implicit_control_indexes.add(
            nested_controls[0]
        )

    duplicate_targets = sorted(
        target
        for target, count in Counter(
            explicit_targets
        ).items()
        if count > 1
    )

    for target in duplicate_targets:
        errors.append(
            f"{source_name}: label[for={target}]が"
            "重複しています。"
        )

    explicit_target_set = set(
        explicit_targets
    )

    for index, control in enumerate(
        parser.controls
    ):
        control_id = control["id"]
        has_explicit_label = (
            isinstance(control_id, str)
            and control_id
            in explicit_target_set
        )
        has_implicit_label = (
            index
            in implicit_control_indexes
        )
        has_aria_name = any(
            isinstance(control[name], str)
            and bool(control[name].strip())
            for name in (
                "aria-label",
                "aria-labelledby",
            )
        )

        if (
            has_explicit_label
            or has_implicit_label
            or has_aria_name
        ):
            continue

        errors.append(
            f"{source_name}:{control['line']}: "
            f"{control['tag']} controlに"
            "関連付けられたlabelがありません。"
        )

    return errors


def normalized_contract_path(raw_path: str) -> str:
    normalized = unquote(raw_path).replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    return normalized


class TemplateReferenceTests(unittest.TestCase):
    def test_local_references_resolve(self) -> None:
        template_files = sorted(
            TEMPLATES_ROOT.rglob("*.html")
        )

        self.assertTrue(
            template_files,
            "テンプレHTMLが見つかりません。",
        )

        parsed_templates = {
            path.resolve(): parse_template(path)
            for path in template_files
        }
        template_root = TEMPLATES_ROOT.resolve()
        generated_dist_references: set[str] = set()
        errors: list[str] = []

        for html_path in template_files:
            parser = parsed_templates[html_path.resolve()]

            for (
                line_number,
                tag,
                attribute_name,
                value,
            ) in parser.references:
                parsed_url = urlsplit(value)

                if parsed_url.scheme or parsed_url.netloc:
                    continue

                if (
                    not parsed_url.path
                    and not parsed_url.fragment
                ):
                    errors.append(
                        (
                            f"{html_path.relative_to(TEMPLATES_ROOT)}"
                            f":{line_number}: "
                            f"{tag}[{attribute_name}]が空です。"
                        )
                    )
                    continue

                target_path = html_path

                if parsed_url.path:
                    contract_path = normalized_contract_path(
                        parsed_url.path
                    )

                    if (
                        contract_path
                        in GENERATED_DIST_REFERENCES
                    ):
                        generated_dist_references.add(
                            contract_path
                        )
                        continue

                    target_path = (
                        html_path.parent
                        / unquote(parsed_url.path)
                    ).resolve()

                    try:
                        target_path.relative_to(template_root)
                    except ValueError:
                        errors.append(
                            (
                                f"{html_path.relative_to(TEMPLATES_ROOT)}"
                                f":{line_number}: "
                                f"テンプレ外を参照しています: {value}"
                            )
                        )
                        continue

                    if not target_path.is_file():
                        errors.append(
                            (
                                f"{html_path.relative_to(TEMPLATES_ROOT)}"
                                f":{line_number}: "
                                f"参照先が存在しません: {value}"
                            )
                        )
                        continue

                if parsed_url.fragment:
                    target_parser = parsed_templates.get(
                        target_path.resolve()
                    )

                    if target_parser is None:
                        errors.append(
                            (
                                f"{html_path.relative_to(TEMPLATES_ROOT)}"
                                f":{line_number}: "
                                f"HTML以外へのfragment参照です: "
                                f"{value}"
                            )
                        )
                        continue

                    fragment = unquote(parsed_url.fragment)

                    if fragment not in target_parser.ids:
                        errors.append(
                            (
                                f"{html_path.relative_to(TEMPLATES_ROOT)}"
                                f":{line_number}: "
                                f"fragment先が存在しません: {value}"
                            )
                        )

        if (
            generated_dist_references
            != GENERATED_DIST_REFERENCES
        ):
            errors.append(
                (
                    "生成dist参照が契約と一致しません。"
                    f" expected={sorted(GENERATED_DIST_REFERENCES)}"
                    f" actual={sorted(generated_dist_references)}"
                )
            )

        self.assertEqual(
            [],
            errors,
            "\n" + "\n".join(errors),
        )

    def test_runtime_tokens_match_templates(
        self,
    ) -> None:
        contract = json.loads(
            (
                REPOSITORY_ROOT
                / "starter-contract.json"
            ).read_text(encoding="utf-8")
        )

        runtime_tokens = contract.get(
            "requiredRuntimeTokens"
        )

        self.assertIsInstance(
            runtime_tokens,
            list,
        )
        self.assertTrue(runtime_tokens)

        template_classes: set[str] = set()
        template_ids: set[str] = set()
        template_texts: list[str] = []

        for html_path in sorted(
            TEMPLATES_ROOT.rglob("*.html")
        ):
            parser = parse_template(html_path)
            template_classes.update(parser.classes)
            template_ids.update(parser.ids)
            template_texts.append(
                html_path.read_text(encoding="utf-8")
            )

        combined_template_text = "\n".join(
            template_texts
        )
        missing_tokens: list[str] = []

        for token in runtime_tokens:
            if token.startswith("."):
                if token[1:] not in template_classes:
                    missing_tokens.append(token)
            elif token.startswith("#"):
                if token[1:] not in template_ids:
                    missing_tokens.append(token)
            elif token not in combined_template_text:
                missing_tokens.append(token)

        declared_js_hooks = {
            token[1:]
            for token in runtime_tokens
            if token.startswith(".js-")
        }

        template_js_hooks = {
            class_name
            for class_name in template_classes
            if class_name.startswith("js-")
        }

        undeclared_js_hooks = sorted(
            template_js_hooks - declared_js_hooks
        )

        self.assertEqual(
            [],
            missing_tokens,
            (
                "契約tokenがテンプレにありません: "
                f"{missing_tokens}"
            ),
        )
        self.assertEqual(
            [],
            undeclared_js_hooks,
            (
                "契約されていないjs-* hookがあります: "
                f"{undeclared_js_hooks}"
            ),
        )
        self.assertNotIn(
            "js-site-nav",
            template_classes,
        )

    def test_ids_are_unique_per_document(self) -> None:
        duplicates: list[str] = []

        for html_path in sorted(
            TEMPLATES_ROOT.rglob("*.html")
        ):
            parser = parse_template(html_path)
            counts = Counter(parser.ids)

            duplicate_ids = sorted(
                element_id
                for element_id, count in counts.items()
                if count > 1
            )

            if duplicate_ids:
                duplicates.append(
                    (
                        f"{html_path.relative_to(TEMPLATES_ROOT)}: "
                        f"{', '.join(duplicate_ids)}"
                    )
                )

        self.assertEqual(
            [],
            duplicates,
            "\n" + "\n".join(duplicates),
        )


class TemplateHeroContractTests(
    unittest.TestCase
):
    def assert_website_hero_contract(
        self,
        path: Path,
    ) -> None:
        parser = parse_hero_contract(path)

        self.assertEqual(1, parser.hero_count)
        self.assertEqual(
            1,
            parser.hero_content_count,
        )
        self.assertEqual(
            1,
            parser.hero_actions_count,
        )
        self.assertEqual(
            [],
            parser.overlay_interactive_elements,
        )
        self.assertTrue(
            parser.hero_classes.isdisjoint(
                {
                    "u-flex",
                    "u-flex-sp-col",
                    "u-flex-wrap",
                }
            )
        )
        self.assertEqual(
            [
                "./contact.html",
                "./service.html",
            ],
            [
                link["href"]
                for link in parser.hero_action_links
            ],
        )
        self.assertEqual(
            [
                "お問い合わせ導線を確認",
                "サービスページを見る",
            ],
            [
                " ".join(
                    str(link["text"]).split()
                )
                for link in parser.hero_action_links
            ],
        )

    def test_hero_overlays_are_non_interactive(
        self,
    ) -> None:
        errors: list[str] = []

        for path in sorted(
            TEMPLATES_ROOT.rglob("*.html")
        ):
            parser = parse_hero_contract(path)
            relative_path = path.relative_to(
                TEMPLATES_ROOT
            ).as_posix()

            for line_number, tag in (
                parser.overlay_interactive_elements
            ):
                errors.append(
                    f"{relative_path}:{line_number}: "
                    "c-hero__overlay内に"
                    f"interactive element <{tag}>があります。"
                )

        self.assertEqual(
            [],
            errors,
            "\n" + "\n".join(errors),
        )

    def test_hero_overlay_validator_rejects_interactive_elements(
        self,
    ) -> None:
        parser = parse_hero_contract_text(
            """
            <div class="c-hero__overlay">
              <a href="/">Link</a>
              <button type="button">Button</button>
              <input type="text" />
              <select><option>Option</option></select>
              <textarea></textarea>
              <summary>Summary</summary>
              <span tabindex="-1">Focusable</span>
            </div>
            """
        )

        self.assertEqual(
            [
                "a",
                "button",
                "input",
                "select",
                "textarea",
                "summary",
                "span",
            ],
            [
                tag
                for _, tag in (
                    parser.overlay_interactive_elements
                )
            ],
        )

    def test_website_index_uses_canonical_hero_contract(
        self,
    ) -> None:
        self.assert_website_hero_contract(
            TEMPLATES_ROOT
            / "website"
            / "index.html"
        )

    def test_generated_website_preserves_hero_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_dir = root / "project-generator"
            template_dir = (
                base_dir
                / "templates"
                / "website"
            )
            shutil.copytree(
                TEMPLATES_ROOT / "website",
                template_dir,
            )

            dist_root = (
                root
                / "sass-starter-exiga"
                / "dist"
            )
            (dist_root / "css").mkdir(
                parents=True
            )
            (dist_root / "js" / "core").mkdir(
                parents=True
            )
            (
                dist_root
                / "css"
                / "main.css"
            ).write_text(
                "/* test css */\n",
                encoding="utf-8",
            )
            (
                dist_root
                / "js"
                / "core"
                / "app.js"
            ).write_text(
                "export {};\n",
                encoding="utf-8",
            )

            with patch.object(
                script,
                "resolve_exiga_dist",
                return_value=dist_root,
            ):
                output_dir = script.create_project(
                    base_dir=base_dir,
                    template_name="website",
                    project_name="Hero Contract",
                    force=True,
                )

            self.assert_website_hero_contract(
                output_dir / "index.html"
            )


class TemplateProductContractTests(
    unittest.TestCase
):
    def assert_shop_product_contract(
        self,
        path: Path,
        *,
        require_generated_body_classes: bool = False,
    ) -> ProductListingParser:
        text = path.read_text(encoding="utf-8")
        parser = parse_product_listing_text(text)

        self.assertEqual(
            [],
            product_listing_contract_errors(
                text,
                expected_grid_count=3,
                expected_product_count=21,
            ),
        )
        self.assertEqual(
            EXPECTED_SHOP_GRID_CARD_COUNTS,
            [
                len(card_indexes)
                for card_indexes in (
                    parser.grid_card_indexes
                )
            ],
        )
        self.assertEqual(
            EXPECTED_SHOP_PRODUCTS,
            [
                (
                    normalized_text(title),
                    normalized_text(price),
                )
                for title, price in zip(
                    parser.card_titles,
                    parser.card_prices,
                    strict=True,
                )
            ],
        )
        self.assertEqual(
            EXPECTED_SHOP_CATEGORY_IDS,
            parser.category_ids,
        )
        self.assertEqual(
            EXPECTED_SHOP_CATEGORY_HREFS,
            parser.category_hrefs,
        )

        if require_generated_body_classes:
            self.assertTrue(
                {
                    "t-shop",
                    "p-products",
                }.issubset(parser.body_classes)
            )

        return parser

    def test_deprecated_product_classes_are_absent_from_templates(
        self,
    ) -> None:
        errors: list[str] = []

        for path in sorted(
            TEMPLATES_ROOT.rglob("*.html")
        ):
            deprecated_classes = sorted(
                DEPRECATED_PRODUCT_CLASSES
                & set(parse_template(path).classes)
            )

            if deprecated_classes:
                errors.append(
                    f"{path.relative_to(TEMPLATES_ROOT)}: "
                    f"{', '.join(deprecated_classes)}"
                )

        self.assertEqual(
            [],
            errors,
            "\n" + "\n".join(errors),
        )

    def test_product_listing_validator_rejects_invalid_contracts(
        self,
    ) -> None:
        valid_markup = """
        <div class="c-product-grid c-product-grid--cols-4">
          <article class="c-product-card">
            <h3 class="c-product-card__title">Product A</h3>
            <p class="c-product-card__price">100 yen</p>
          </article>
          <article class="c-product-card">
            <h3 class="c-product-card__title">Product B</h3>
            <p class="c-product-card__price">200 yen</p>
          </article>
        </div>
        """
        invalid_cases = {
            "missing-grid-modifier": (
                valid_markup.replace(
                    " c-product-grid--cols-4",
                    "",
                    1,
                ),
                "missing c-product-grid--cols-4",
            ),
            "missing-title": (
                valid_markup.replace(
                    "c-product-card__title",
                    "product-title",
                    1,
                ),
                "missing title",
            ),
            "missing-price": (
                valid_markup.replace(
                    "c-product-card__price",
                    "product-price",
                    1,
                ),
                "missing price",
            ),
            "deprecated-class": (
                valid_markup.replace(
                    "c-product-card__price",
                    "c-product-card__price text-price",
                    1,
                ),
                "deprecated-class:text-price",
            ),
            "missing-product": (
                valid_markup.replace(
                    """
          <article class="c-product-card">
            <h3 class="c-product-card__title">Product B</h3>
            <p class="c-product-card__price">200 yen</p>
          </article>""",
                    "",
                    1,
                ),
                "product-card-count:expected=2 actual=1",
            ),
        }

        for name, (markup, expected_error) in (
            invalid_cases.items()
        ):
            with self.subTest(name=name):
                errors = product_listing_contract_errors(
                    markup,
                    expected_grid_count=1,
                    expected_product_count=2,
                )
                self.assertTrue(
                    any(
                        expected_error in error
                        for error in errors
                    ),
                    errors,
                )

    def test_shop_products_use_canonical_product_contract(
        self,
    ) -> None:
        self.assert_shop_product_contract(
            TEMPLATES_ROOT
            / "shop"
            / "products.html"
        )

    def test_generated_shop_preserves_product_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_dir = root / "project-generator"
            template_dir = (
                base_dir
                / "templates"
                / "shop"
            )
            shutil.copytree(
                TEMPLATES_ROOT / "shop",
                template_dir,
            )
            starter_dist = STARTER_ROOT / "dist"

            with patch.object(
                script,
                "resolve_exiga_dist",
                return_value=starter_dist,
            ):
                output_dir = script.create_project(
                    base_dir=base_dir,
                    template_name="shop",
                    project_name="Product Contract",
                    force=True,
                )

            self.assert_shop_product_contract(
                output_dir / "products.html",
                require_generated_body_classes=True,
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

    def test_product_grid_responsive_contract_matches_starter(
        self,
    ) -> None:
        grid_source = (
            STARTER_ROOT
            / "src/scss/components/grid/_grid-product.scss"
        ).read_text(encoding="utf-8")
        breakpoint_source = (
            STARTER_ROOT
            / "src/scss/abstracts/_breakpoints.scss"
        ).read_text(encoding="utf-8")
        compiled_css = (
            STARTER_ROOT / "dist/css/main.css"
        ).read_text(encoding="utf-8")
        desktop_source, responsive_source = (
            grid_source.split(
                "@include u.mq-down(md)",
                maxsplit=1,
            )
        )
        desktop_bodies = css_rule_bodies(
            desktop_source,
            ".c-product-grid--cols-4",
        )
        responsive_bodies = css_rule_bodies(
            responsive_source,
            ".c-product-grid--cols-4",
        )
        compiled_bodies = css_rule_bodies(
            compiled_css,
            ".c-product-grid--cols-4",
        )

        self.assertTrue(
            any(
                "grid-template-columns: "
                "var(--ui-grid-template-cols-4)"
                in body
                for body in desktop_bodies
            ),
            desktop_bodies,
        )
        self.assertTrue(
            any(
                "grid-template-columns: "
                "var(--ui-grid-template-cols-2)"
                in body
                for body in responsive_bodies
            ),
            responsive_bodies,
        )
        self.assertRegex(
            breakpoint_source,
            r"md:\s*768px",
        )
        self.assertTrue(
            any(
                "grid-template-columns: "
                "var(--ui-grid-template-cols-4)"
                in body
                for body in compiled_bodies
            ),
            compiled_bodies,
        )
        self.assertTrue(
            any(
                "grid-template-columns: "
                "var(--ui-grid-template-cols-2)"
                in body
                for body in compiled_bodies
            ),
            compiled_bodies,
        )
        self.assertRegex(
            compiled_css,
            r"@media[^\r\n{]*"
            r"\(width\s*<=\s*767px\)",
        )


class TemplateAccessibilityTests(
    unittest.TestCase
):
    def test_form_controls_have_matching_labels(
        self,
    ) -> None:
        errors: list[str] = []

        for path in sorted(
            TEMPLATES_ROOT.rglob("*.html")
        ):
            relative_path = path.relative_to(
                TEMPLATES_ROOT
            ).as_posix()
            errors.extend(
                form_accessibility_errors(
                    path.read_text(
                        encoding="utf-8"
                    ),
                    source_name=relative_path,
                )
            )

        self.assertEqual(
            [],
            errors,
            "\n" + "\n".join(errors),
        )

    def test_form_label_validator_rejects_broken_relationships(
        self,
    ) -> None:
        errors = form_accessibility_errors(
            """
            <form>
              <label for="missing">Missing</label>
              <label for="email">Email one</label>
              <label for="email">Email two</label>
              <input id="email" type="email" />
              <input id="name" type="text" />
            </form>
            """,
            source_name="fixture.html",
        )

        combined = "\n".join(errors)

        self.assertIn(
            "label[for=missing]",
            combined,
        )
        self.assertIn(
            "label[for=email]が重複",
            combined,
        )
        self.assertIn(
            "input controlに関連付けられたlabel",
            combined,
        )

    def test_lists_and_wrapping_labels_use_valid_accessible_markup(
        self,
    ) -> None:
        template_root = (
            Path(__file__).resolve()
            .parents[1]
            / "templates"
        )

        ol_aria_label_pattern = re.compile(
            r"<ol\b[^>]*\baria-label=",
            flags=re.IGNORECASE,
        )
        wrapping_label_for_pattern = (
            re.compile(
                r"<label\b"
                r"(?=[^>]*\bfor=)"
                r"[^>]*>"
                r"(?:(?!</label>).)*?"
                r"<input\b",
                flags=(
                    re.IGNORECASE
                    | re.DOTALL
                ),
            )
        )

        for path in sorted(
            template_root.rglob("*.html")
        ):
            with self.subTest(
                template=(
                    path.relative_to(
                        template_root
                    ).as_posix()
                )
            ):
                text = path.read_text(
                    encoding="utf-8"
                )

                self.assertIsNone(
                    ol_aria_label_pattern.search(
                        text
                    )
                )
                self.assertIsNone(
                    wrapping_label_for_pattern.search(
                        text
                    )
                )


if __name__ == "__main__":
    unittest.main()
