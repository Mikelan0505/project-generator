from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import script
from test_template_references import (
    form_accessibility_errors,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"
LP_INDEX = TEMPLATES_ROOT / "lp" / "index.html"
STARTER_ROOT = REPOSITORY_ROOT.parent / "sass-starter-exiga"
DEPRECATED_ACCORDION_CLASSES = {
    "c-accordion__trigger",
    "c-accordion__trigger--with-prefix",
    "c-accordion__label",
    "c-accordion__inner",
    "u-anim-dir-up",
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
EXPECTED_FAQ = [
    (
        "初回相談は無料ですか？",
        "無料相談、見積相談、初回ヒアリングなどに差し替えて利用できます。",
        "faq-a1",
        "1",
    ),
    (
        "どの段階から相談できますか？",
        "情報整理前でも相談可能、といった安心材料を入れる想定です。",
        "faq-a2",
        None,
    ),
    (
        "対応エリアや対象範囲は？",
        "エリア、業種、対応業務の範囲など、実案件向けに差し替えてください。",
        "faq-a3",
        None,
    ),
]


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None]
    parent: Element | None = None
    children: list[Element | str] = field(
        default_factory=list
    )

    @property
    def classes(self) -> set[str]:
        return set(
            (self.attrs.get("class") or "").split()
        )


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.document = Element("#document", {})
        self.stack = [self.document]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.add_element(
            tag,
            attrs,
            push=tag.lower() not in HTML_VOID_ELEMENTS,
        )

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.add_element(tag, attrs, push=False)

    def add_element(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        push: bool,
    ) -> None:
        parent = self.stack[-1]
        element = Element(
            tag.lower(),
            dict(attrs),
            parent=parent,
        )
        parent.children.append(element)

        if push:
            self.stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()

        for index in range(
            len(self.stack) - 1,
            0,
            -1,
        ):
            if self.stack[index].tag != normalized_tag:
                continue

            del self.stack[index:]
            return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_document(text: str) -> Element:
    parser = DocumentParser()
    parser.feed(text)
    parser.close()
    return parser.document


def walk(element: Element):
    for child in element.children:
        if not isinstance(child, Element):
            continue

        yield child
        yield from walk(child)


def element_children(element: Element) -> list[Element]:
    return [
        child
        for child in element.children
        if isinstance(child, Element)
    ]


def normalized_text(text: str) -> str:
    return " ".join(text.split())


def visible_text(element: Element) -> str:
    if element.attrs.get("aria-hidden") == "true":
        return ""

    parts: list[str] = []

    for child in element.children:
        if isinstance(child, str):
            parts.append(child)
        else:
            parts.append(visible_text(child))

    return normalized_text(" ".join(parts))


def elements_with_class(
    element: Element,
    class_name: str,
) -> list[Element]:
    return [
        candidate
        for candidate in walk(element)
        if class_name in candidate.classes
    ]


def direct_children_with_class(
    element: Element,
    class_name: str,
) -> list[Element]:
    return [
        child
        for child in element_children(element)
        if class_name in child.classes
    ]


def accordion_root_and_items(
    document: Element,
) -> tuple[list[Element], list[Element]]:
    roots = elements_with_class(
        document,
        "c-accordion",
    )
    items = (
        direct_children_with_class(
            roots[0],
            "c-accordion__item",
        )
        if len(roots) == 1
        else []
    )
    return roots, items


def accordion_contract_errors(
    text: str,
    *,
    expected_item_count: int,
) -> list[str]:
    document = parse_document(text)
    errors = [
        f"deprecated-class:{class_name}"
        for class_name in sorted(
            DEPRECATED_ACCORDION_CLASSES
            & {
                class_name
                for element in walk(document)
                for class_name in element.classes
            }
        )
    ]
    roots, items = accordion_root_and_items(document)

    if len(roots) != 1:
        errors.append(
            "accordion-root-count:"
            f"expected=1 actual={len(roots)}"
        )
        return errors

    all_items = elements_with_class(
        roots[0],
        "c-accordion__item",
    )

    if len(items) != len(all_items):
        errors.append("accordion-item:not direct child")

    if len(items) != expected_item_count:
        errors.append(
            "accordion-item-count:"
            f"expected={expected_item_count} "
            f"actual={len(items)}"
        )

    ids = [
        element_id
        for element in walk(roots[0])
        if (element_id := element.attrs.get("id"))
    ]

    for element_id in sorted(set(ids)):
        if ids.count(element_id) > 1:
            errors.append(f"duplicate-id:{element_id}")

    for owner in walk(roots[0]):
        if (
            "aria-expanded" in owner.attrs
            and "c-accordion__header"
            not in owner.classes
        ):
            errors.append(
                "aria-expanded-owner:"
                f"{owner.tag}"
            )

    controlled_ids: list[str] = []

    for index, item in enumerate(items, start=1):
        children = element_children(item)
        headers = direct_children_with_class(
            item,
            "c-accordion__header",
        )
        contents = direct_children_with_class(
            item,
            "c-accordion__content",
        )

        if len(headers) != 1:
            errors.append(
                f"item-{index}:header-count:{len(headers)}"
            )

        if len(contents) != 1:
            errors.append(
                f"item-{index}:content-count:{len(contents)}"
            )

        if not headers or not contents:
            continue

        header = headers[0]
        content = contents[0]

        if header.tag != "button":
            errors.append(
                f"item-{index}:header-tag:{header.tag}"
            )

        if header.attrs.get("type") != "button":
            errors.append(
                f"item-{index}:header-type"
            )

        if any(
            descendant.tag == "button"
            for descendant in walk(header)
        ):
            errors.append(
                f"item-{index}:nested-button"
            )

        expanded = header.attrs.get("aria-expanded")

        if expanded not in {"true", "false"}:
            errors.append(
                f"item-{index}:missing aria-expanded"
            )

        controls = header.attrs.get("aria-controls")

        if not controls:
            errors.append(
                f"item-{index}:missing aria-controls"
            )
        else:
            controlled_ids.append(controls)

        content_id = content.attrs.get("id")

        if not content_id or controls != content_id:
            errors.append(
                f"item-{index}:aria-controls target missing"
            )

        if (
            children.index(content)
            != children.index(header) + 1
        ):
            errors.append(
                f"item-{index}:content not after header"
            )

        if "aria-expanded" in content.attrs:
            errors.append(
                f"item-{index}:content owns aria-expanded"
            )

        hidden = "hidden" in content.attrs

        if expanded == "true" and hidden:
            errors.append(
                f"item-{index}:expanded content hidden"
            )

        if expanded == "false" and not hidden:
            errors.append(
                f"item-{index}:collapsed content visible"
            )

        default_open = (
            item.attrs.get("data-open") == "1"
        )

        if expanded in {"true", "false"} and (
            (expanded == "true") != default_open
        ):
            errors.append(
                f"item-{index}:data-open mismatch"
            )

        icons = elements_with_class(
            header,
            "c-accordion__icon",
        )

        if len(icons) != 1:
            errors.append(
                f"item-{index}:icon-count:{len(icons)}"
            )

        if not element_children(content):
            errors.append(
                f"item-{index}:content child missing"
            )

    for controlled_id in sorted(set(controlled_ids)):
        if controlled_ids.count(controlled_id) > 1:
            errors.append(
                f"duplicate-aria-controls:{controlled_id}"
            )

    return errors


def accordion_snapshot(
    text: str,
) -> list[tuple[str, str, str | None, str | None]]:
    document = parse_document(text)
    _, items = accordion_root_and_items(document)
    snapshot = []

    for item in items:
        header = direct_children_with_class(
            item,
            "c-accordion__header",
        )[0]
        content = direct_children_with_class(
            item,
            "c-accordion__content",
        )[0]
        snapshot.append(
            (
                visible_text(header),
                visible_text(content),
                content.attrs.get("id"),
                item.attrs.get("data-open"),
            )
        )

    return snapshot


def generated_reference_errors(
    output_dir: Path,
) -> list[str]:
    html_paths = sorted(output_dir.rglob("*.html"))
    documents = {
        path.resolve(): parse_document(
            path.read_text(encoding="utf-8")
        )
        for path in html_paths
    }
    errors: list[str] = []

    for html_path in html_paths:
        document = documents[html_path.resolve()]
        ids = [
            element_id
            for element in walk(document)
            if (element_id := element.attrs.get("id"))
        ]

        for element_id in sorted(set(ids)):
            if ids.count(element_id) > 1:
                errors.append(
                    f"{html_path.name}:duplicate-id:{element_id}"
                )

        for element in walk(document):
            for attribute in ("href", "src"):
                value = element.attrs.get(attribute)

                if not value:
                    continue

                parsed_url = urlsplit(value)

                if parsed_url.scheme or parsed_url.netloc:
                    continue

                if not parsed_url.path and not parsed_url.fragment:
                    continue

                target = (
                    html_path
                    if not parsed_url.path
                    else (
                        html_path.parent
                        / unquote(parsed_url.path)
                    ).resolve()
                )

                if (
                    not target.is_relative_to(
                        output_dir.resolve()
                    )
                    or not target.exists()
                ):
                    errors.append(
                        f"{html_path.name}:missing:{value}"
                    )
                    continue

                if (
                    parsed_url.fragment
                    and target.suffix.lower() == ".html"
                ):
                    target_document = documents.get(
                        target.resolve()
                    )
                    target_ids = {
                        element.attrs.get("id")
                        for element in walk(
                            target_document
                        )
                    } if target_document else set()

                    if (
                        unquote(parsed_url.fragment)
                        not in target_ids
                    ):
                        errors.append(
                            f"{html_path.name}:"
                            f"missing-fragment:{value}"
                        )

    return errors


VALID_ITEM_1 = """
  <div class="c-accordion__item" data-open="1">
    <button class="c-accordion__header" type="button" aria-expanded="true" aria-controls="fixture-a1">
      <span>Question 1</span>
      <span class="c-accordion__icon" aria-hidden="true"></span>
    </button>
    <div id="fixture-a1" class="c-accordion__content"><div><p>Answer 1</p></div></div>
  </div>
"""
VALID_ITEM_2 = """
  <div class="c-accordion__item">
    <button class="c-accordion__header" type="button" aria-expanded="false" aria-controls="fixture-a2">
      <span>Question 2</span>
      <span class="c-accordion__icon" aria-hidden="true"></span>
    </button>
    <div id="fixture-a2" class="c-accordion__content" hidden><div><p>Answer 2</p></div></div>
  </div>
"""
VALID_MARKUP = (
    '<div class="c-accordion">'
    f"{VALID_ITEM_1}{VALID_ITEM_2}"
    "</div>"
)


class TemplateAccordionTests(unittest.TestCase):
    def assert_lp_accordion_contract(
        self,
        path: Path,
        *,
        generated: bool = False,
    ) -> None:
        text = path.read_text(encoding="utf-8")
        self.assertEqual(
            [],
            accordion_contract_errors(
                text,
                expected_item_count=3,
            ),
        )
        self.assertEqual(EXPECTED_FAQ, accordion_snapshot(text))

        if generated:
            document = parse_document(text)
            bodies = [
                element
                for element in walk(document)
                if element.tag == "body"
            ]
            self.assertEqual(1, len(bodies))
            self.assertTrue(
                {"t-lp", "p-home"}.issubset(
                    bodies[0].classes
                )
            )

    def test_lp_uses_canonical_accordion_contract(
        self,
    ) -> None:
        self.assert_lp_accordion_contract(LP_INDEX)

    def test_deprecated_accordion_classes_are_absent_from_templates(
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
                DEPRECATED_ACCORDION_CLASSES
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

    def test_accordion_validator_rejects_invalid_contracts(
        self,
    ) -> None:
        invalid_cases = {
            "heading-header": (
                VALID_MARKUP.replace(
                    '<button class="c-accordion__header"',
                    '<h3 class="c-accordion__header"',
                    1,
                ).replace("</button>", "</h3>", 1),
                "header-tag:h3",
            ),
            "nested-button": (
                VALID_MARKUP.replace(
                    "<span>Question 1</span>",
                    "<span>Question 1</span>"
                    '<button type="button">Nested</button>',
                    1,
                ),
                "nested-button",
            ),
            "missing-expanded": (
                VALID_MARKUP.replace(
                    ' aria-expanded="true"',
                    "",
                    1,
                ),
                "missing aria-expanded",
            ),
            "missing-controls-target": (
                VALID_MARKUP.replace(
                    'aria-controls="fixture-a1"',
                    'aria-controls="missing"',
                    1,
                ),
                "aria-controls target missing",
            ),
            "collapsed-content-visible": (
                VALID_MARKUP.replace(
                    'class="c-accordion__content" hidden',
                    'class="c-accordion__content"',
                    1,
                ),
                "collapsed content visible",
            ),
            "expanded-content-hidden": (
                VALID_MARKUP.replace(
                    'id="fixture-a1" '
                    'class="c-accordion__content"',
                    'id="fixture-a1" '
                    'class="c-accordion__content" hidden',
                    1,
                ),
                "expanded content hidden",
            ),
            "content-not-adjacent": (
                VALID_MARKUP.replace(
                    "</button>\n    <div id=\"fixture-a1\"",
                    "</button><p>Gap</p>\n    "
                    '<div id="fixture-a1"',
                    1,
                ),
                "content not after header",
            ),
            "deprecated-class": (
                VALID_MARKUP.replace(
                    "<span>Question 1</span>",
                    '<span class="c-accordion__label">'
                    "Question 1</span>",
                    1,
                ),
                "deprecated-class:c-accordion__label",
            ),
            "missing-item": (
                VALID_MARKUP.replace(
                    VALID_ITEM_2,
                    "",
                    1,
                ),
                "accordion-item-count:expected=2 actual=1",
            ),
        }

        for name, (markup, expected_error) in (
            invalid_cases.items()
        ):
            with self.subTest(name=name):
                errors = accordion_contract_errors(
                    markup,
                    expected_item_count=2,
                )
                self.assertTrue(
                    any(
                        expected_error in error
                        for error in errors
                    ),
                    errors,
                )

    def test_starter_javascript_matches_template_contract(
        self,
    ) -> None:
        javascript = (
            STARTER_ROOT
            / "src/js/components/accordion.js"
        ).read_text(encoding="utf-8")
        app_javascript = (
            STARTER_ROOT / "src/js/core/app.js"
        ).read_text(encoding="utf-8")
        semantic_patterns = {
            "header lookup": (
                r"(?:const|let)\s+header\s*=\s*"
                r"item\.querySelector\(\s*"
                r"['\"]\.c-accordion__header['\"]\s*\)"
            ),
            "content lookup": (
                r"(?:const|let)\s+content\s*=\s*"
                r"item\.querySelector\(\s*"
                r"['\"]\.c-accordion__content['\"]\s*\)"
            ),
            "header click listener": (
                r"header\.addEventListener\(\s*"
                r"['\"]click['\"]\s*,"
            ),
            "header expanded update": (
                r"header\.setAttribute\(\s*"
                r"['\"]aria-expanded['\"]\s*,"
            ),
            "header controls update": (
                r"header\.setAttribute\(\s*"
                r"['\"]aria-controls['\"]\s*,"
            ),
            "content hidden update": (
                r"content\.hidden\s*="
            ),
            "data-open initialization": (
                r"item\.getAttribute\(\s*"
                r"['\"]data-open['\"]\s*\)\s*===\s*"
                r"['\"]1['\"]"
            ),
        }

        for name, pattern in semantic_patterns.items():
            with self.subTest(name=name):
                self.assertRegex(javascript, pattern)

        self.assertRegex(
            app_javascript,
            r"initAccordion\(\)",
        )

    def test_generated_lp_preserves_accordion_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="pg-html-003-"
        ) as temp:
            temp_path = Path(temp)
            base_dir = temp_path / "project-generator"
            shutil.copytree(
                TEMPLATES_ROOT / "lp",
                base_dir / "templates" / "lp",
            )
            starter_dist = STARTER_ROOT / "dist"

            with patch.object(
                script,
                "resolve_exiga_dist",
                return_value=starter_dist,
            ):
                output_dir = script.create_project(
                    base_dir=base_dir,
                    template_name="lp",
                    project_name="Accordion Contract",
                    force=True,
                )

            self.assert_lp_accordion_contract(
                output_dir / "index.html",
                generated=True,
            )
            self.assertEqual(
                [],
                generated_reference_errors(output_dir),
            )
            self.assertEqual(
                [],
                form_accessibility_errors(
                    (
                        output_dir / "index.html"
                    ).read_text(encoding="utf-8"),
                    source_name="index.html",
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
