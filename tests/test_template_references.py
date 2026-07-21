from __future__ import annotations

import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import unittest
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"

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
