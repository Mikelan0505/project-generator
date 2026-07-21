from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = REPOSITORY_ROOT / "templates"

GENERATED_DIST_REFERENCES = {
    "dist/css/main.css",
    "dist/js/core/app.js",
}


class TemplateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
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


if __name__ == "__main__":
    unittest.main()
