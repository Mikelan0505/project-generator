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
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
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
        elements_with_class,
        generated_reference_errors,
        parse_document,
        visible_text,
        walk,
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
FORBIDDEN_CLASSES = {
    "c-card--fill",
    "flow-list--arrow",
    "flow-list__title-text",
    "site-header--scroll-light",
    "u-measure-840",
}
TEMPLATE_PATHS = (
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
WEBSITE_PATHS = {
    path for path in TEMPLATE_PATHS if path.startswith("website/")
}
SHOP_PATHS = {
    path for path in TEMPLATE_PATHS if path.startswith("shop/")
}
HEADER_CLASSES = (
    "is-sticky",
    "site-header",
    "site-header--drawer",
    "site-header--solid",
)
HEADER_CONTRACTS = {
    "website": (
        "{{PROJECT}} トップ 会社案内 サービス お問い合わせ",
        (
            "./index.html",
            "./index.html",
            "./about.html",
            "./service.html",
            "./contact.html",
        ),
    ),
    "shop": (
        "{{PROJECT}} トップ 商品一覧 店舗案内 お問い合わせ",
        (
            "./index.html",
            "./index.html",
            "./products.html",
            "./about.html",
            "./contact.html",
        ),
    ),
    "lp": (
        "{{PROJECT}} 課題 特徴 提供内容 信頼材料 流れ FAQ お問い合わせ",
        (
            "#top",
            "#problem",
            "#solution",
            "#offer",
            "#proof",
            "#flow",
            "#faq",
            "#cta",
        ),
    ),
}
CARD_TEXTS = {
    "website/index.html": (
        "SERVICE 01 主力サービス 最優先で見せたいサービスの概要を記載します。詳細はサービスページに誘導します。",
        "SERVICE 02 関連サービス 周辺サービスやセット提案、対応範囲などを簡潔に載せるための枠です。",
        "SERVICE 03 サポート内容 導入支援、制作後運用、保守体制など、案件に応じて差し替えて使います。",
    ),
    "shop/index.html": (
        "人気商品 定番ギフトセット 初めての方にも案内しやすい代表商品です。焼き菓子、雑貨、豆の詰め合わせなどに差し替えられます。 税込 3,240円",
        "季節限定 季節のおすすめ 旬素材、限定パッケージ、イベント向け商品など、差し替えのしやすい注力枠です。 税込 1,620円",
        "定番商品 日常使いの一品 リピート購入につながりやすい主力商品や、日常向けの売れ筋商品紹介に向いています。 税込 864円",
        "CATEGORY 01 贈り物向け ギフトボックス、ラッピング対応商品、季節の贈答品などをまとめる枠です。",
        "CATEGORY 02 日常向け 毎日使いやすい価格帯の商品、定番商品、まとめ買い向けの商品紹介に使えます。",
        "CATEGORY 03 季節商品 期間限定、イベント向け、季節素材の展開など、更新頻度の高いカテゴリ向けです。",
    ),
    "shop/about.html": (
        "POINT 01 商品選び 素材や作り手、使い心地など、店の基準に合わせて差し替えやすい説明枠です。",
        "POINT 02 贈り物対応 ラッピング、用途提案、季節提案など、物販店らしい接客軸を見せる用途に向きます。",
        "POINT 03 店内体験 香り、手に取る楽しさ、選ぶ時間など、来店価値を伝えるための枠です。",
    ),
    "lp/index.html": (
        "FEATURE 01 要件整理から支援 はじめての依頼でも相談しやすい進め方に差し替えて利用します。",
        "FEATURE 02 実行まで一貫対応 提案だけで終わらず、実装や運用まで伴走する訴求に向いています。",
        "FEATURE 03 成果を見ながら改善 継続支援や改善提案を価値として見せたいときに使う枠です。",
        "PLAN 01 基本プラン まず案内したい標準プランの説明枠です。",
        "PLAN 02 おすすめプラン 最も訴求したいオファーを中央に置く使い方を想定しています。",
        "PLAN 03 拡張プラン 保守、追加支援、上位支援などをここに配置できます。",
        "PROOF 01 実績数 導入件数や継続率など、数字で見せやすい要素を入れます。",
        "PROOF 02 支援事例 代表的な案件や改善例を簡潔に載せると信頼補強になります。",
        "PROOF 03 運営情報 会社概要や担当体制、サポート範囲などへ差し替えて使えます。",
    ),
}
NOTICE_TEXTS = {
    "shop/index.html": (
        "差し替えメモ 店舗写真や商品写真を使う場合は `./assets/img/` に配置して差し替えてください。 "
        "ケーキ店、焼き菓子店、コーヒー豆店、雑貨店、ギフトショップなどに流用しやすい文量にしています。"
    ),
    "shop/about.html": (
        "差し替えメモ 創業背景、店主の想い、産地や作り手への考え方などに差し替えて利用できます。 "
        "ブランドのトーンに応じて、やさしい語り口にも、専門性を感じる文面にも調整しやすい量にしています。"
    ),
}
FLOW_TITLES = (
    "ヒアリング",
    "提案",
    "制作・実行",
    "納品・運用",
)
FLOW_TEXT = (
    "01 ヒアリング 要件、課題、優先順位を確認します。 "
    "02 提案 進め方、内容、概算、体制などを整理して提示します。 "
    "03 制作・実行 決定内容に沿って制作や実作業を進行します。 "
    "04 納品・運用 公開後や導入後の運用支援がある場合はここに記載します。"
)


@dataclass(frozen=True)
class ElementSnapshot:
    template_path: str
    kind: str
    order: int
    tag: str
    parent_component: tuple[str, tuple[str, ...]]
    classes: tuple[str, ...]
    text: str
    hrefs: tuple[str, ...]
    element_id: str | None


def template_name_for(path: str) -> str:
    return path.split("/", 1)[0]


def page_class_for(path: str) -> str:
    stem = Path(path).stem
    return "p-home" if stem == "index" else f"p-{stem}"


def parent_signature(element) -> tuple[str, tuple[str, ...]]:
    if element.parent is None:
        return ("", ())
    return (
        element.parent.tag,
        tuple(sorted(element.parent.classes)),
    )


def element_hrefs(element) -> tuple[str, ...]:
    return tuple(
        href
        for candidate in walk(element)
        if candidate.tag == "a"
        and (href := candidate.attrs.get("href"))
        is not None
    )


def snapshot(
    *,
    template_path: str,
    kind: str,
    order: int,
    element,
) -> ElementSnapshot:
    return ElementSnapshot(
        template_path=template_path,
        kind=kind,
        order=order,
        tag=element.tag,
        parent_component=parent_signature(element),
        classes=tuple(sorted(element.classes)),
        text=visible_text(element),
        hrefs=element_hrefs(element),
        element_id=element.attrs.get("id"),
    )


def expected_header_snapshot(
    path: str,
    *,
    project_name: str | None,
) -> ElementSnapshot:
    template_name = template_name_for(path)
    text, hrefs = HEADER_CONTRACTS[template_name]
    if project_name is not None:
        text = text.replace("{{PROJECT}}", project_name)
        parent_classes = tuple(
            sorted(
                {
                    f"t-{template_name}",
                    page_class_for(path),
                }
            )
        )
    else:
        parent_classes = ()
    return ElementSnapshot(
        template_path=path,
        kind="header",
        order=0,
        tag="header",
        parent_component=("body", parent_classes),
        classes=HEADER_CLASSES,
        text=text,
        hrefs=hrefs,
        element_id="top",
    )


def expected_snapshots(
    path: str,
    *,
    project_name: str | None = None,
) -> list[ElementSnapshot]:
    expected = [
        expected_header_snapshot(
            path,
            project_name=project_name,
        )
    ]
    grid_variant = (
        "l-grid--cards-2xl-3"
        if path == "shop/about.html"
        else "l-grid--cards-3"
    )
    grid_parent = (
        "div",
        (
            "l-grid",
            grid_variant,
            "l-grid--cards-uniform",
        ),
    )
    for order, text in enumerate(CARD_TEXTS.get(path, ())):
        expected.append(
            ElementSnapshot(
                template_path=path,
                kind="card",
                order=order,
                tag="article",
                parent_component=grid_parent,
                classes=("c-card", "c-card--lg"),
                text=text,
                hrefs=(),
                element_id=None,
            )
        )

    if path in NOTICE_TEXTS:
        expected.append(
            ElementSnapshot(
                template_path=path,
                kind="measure-notice",
                order=0,
                tag="div",
                parent_component=(
                    "div",
                    ("c-stack", "l-container"),
                ),
                classes=(
                    "c-notice",
                    "c-notice--soft",
                    "u-measure-860",
                ),
                text=NOTICE_TEXTS[path],
                hrefs=(),
                element_id=None,
            )
        )

    if path == "website/service.html":
        expected.append(
            ElementSnapshot(
                template_path=path,
                kind="flow-list",
                order=0,
                tag="ol",
                parent_component=(
                    "div",
                    ("c-stack", "l-container"),
                ),
                classes=("flow-list",),
                text=FLOW_TEXT,
                hrefs=(),
                element_id=None,
            )
        )
        for order, text in enumerate(FLOW_TITLES):
            expected.append(
                ElementSnapshot(
                    template_path=path,
                    kind="flow-title-wrapper",
                    order=order,
                    tag="span",
                    parent_component=(
                        "h3",
                        ("flow-list__title",),
                    ),
                    classes=(),
                    text=text,
                    hrefs=(),
                    element_id=None,
                )
            )

    return expected


def actual_snapshots(path: str, text: str) -> list[ElementSnapshot]:
    document = parse_document(text)
    actual: list[ElementSnapshot] = []

    headers = elements_with_class(document, "site-header")
    for order, element in enumerate(headers):
        actual.append(
            snapshot(
                template_path=path,
                kind="header",
                order=order,
                element=element,
            )
        )

    if path in CARD_TEXTS:
        cards = elements_with_class(document, "c-card")
        for order, element in enumerate(cards):
            actual.append(
                snapshot(
                    template_path=path,
                    kind="card",
                    order=order,
                    element=element,
                )
            )

    if path in NOTICE_TEXTS:
        notices = elements_with_class(document, "c-notice")
        for order, element in enumerate(notices):
            actual.append(
                snapshot(
                    template_path=path,
                    kind="measure-notice",
                    order=order,
                    element=element,
                )
            )

    if path == "website/service.html":
        roots = elements_with_class(document, "flow-list")
        for order, element in enumerate(roots):
            actual.append(
                snapshot(
                    template_path=path,
                    kind="flow-list",
                    order=order,
                    element=element,
                )
            )

        title_wrappers = [
            child
            for title in elements_with_class(
                document,
                "flow-list__title",
            )
            for child in title.children
            if not isinstance(child, str)
        ]
        for order, element in enumerate(title_wrappers):
            actual.append(
                snapshot(
                    template_path=path,
                    kind="flow-title-wrapper",
                    order=order,
                    element=element,
                )
            )

    return actual


def all_class_tokens(text: str) -> set[str]:
    return {
        class_name
        for element in walk(parse_document(text))
        for class_name in element.classes
    }


def document_contract_errors(
    path: str,
    text: str,
    *,
    project_name: str | None = None,
) -> list[str]:
    errors = [
        f"forbidden-class:{class_name}"
        for class_name in sorted(
            FORBIDDEN_CLASSES & all_class_tokens(text)
        )
    ]
    expected = expected_snapshots(
        path,
        project_name=project_name,
    )
    actual = actual_snapshots(path, text)

    if len(actual) != len(expected):
        errors.append(
            "snapshot-count:"
            f"expected={len(expected)} actual={len(actual)}"
        )

    for index, (expected_item, actual_item) in enumerate(
        zip(expected, actual)
    ):
        if actual_item != expected_item:
            errors.append(
                f"snapshot-{index}:"
                f"expected={expected_item!r} "
                f"actual={actual_item!r}"
            )

    return errors


def token_occurs(text: str, token: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(token)}"
            rf"(?![A-Za-z0-9_-])",
            text,
        )
    )


def rule_bodies(text: str, selector: str) -> list[str]:
    without_comments = re.sub(
        r"/\*.*?\*/",
        "",
        text,
        flags=re.DOTALL,
    )
    return css_rule_bodies(
        re.sub(
            r"@(?:use|forward)\b[^;]+;",
            "",
            without_comments,
        ),
        selector,
    )


def swap_first_two_cards(text: str) -> str:
    pattern = re.compile(
        r"(?P<first><article\b[^>]*\bc-card\b[^>]*>"
        r".*?</article>)"
        r"(?P<space>\s*)"
        r"(?P<second><article\b[^>]*\bc-card\b[^>]*>"
        r".*?</article>)",
        flags=re.DOTALL,
    )
    return pattern.sub(
        lambda match: (
            match.group("second")
            + match.group("space")
            + match.group("first")
        ),
        text,
        count=1,
    )


class TemplateClassContractTests(unittest.TestCase):
    def test_templates_remove_only_deprecated_class_contracts(
        self,
    ) -> None:
        paths = sorted(TEMPLATES_ROOT.rglob("*.html"))
        self.assertEqual(
            TEMPLATE_PATHS,
            tuple(
                path.relative_to(TEMPLATES_ROOT).as_posix()
                for path in paths
            ),
        )

        for path in paths:
            relative_path = path.relative_to(
                TEMPLATES_ROOT
            ).as_posix()
            with self.subTest(path=relative_path):
                self.assertEqual(
                    [],
                    document_contract_errors(
                        relative_path,
                        path.read_text(encoding="utf-8"),
                    ),
                )

    def test_measure_replacements_use_existing_860_contract(
        self,
    ) -> None:
        measured_elements = []
        for path in sorted(TEMPLATES_ROOT.rglob("*.html")):
            document = parse_document(
                path.read_text(encoding="utf-8")
            )
            measured_elements.extend(
                element
                for element in walk(document)
                if "u-measure-860" in element.classes
                and "c-notice" in element.classes
            )

        self.assertEqual(2, len(measured_elements))
        for element in measured_elements:
            self.assertNotIn("style", element.attrs)
            self.assertIn("c-notice", element.classes)

    def test_validator_rejects_contract_regressions(
        self,
    ) -> None:
        website_index = (
            TEMPLATES_ROOT / "website/index.html"
        ).read_text(encoding="utf-8")
        shop_index = (
            TEMPLATES_ROOT / "shop/index.html"
        ).read_text(encoding="utf-8")

        for class_name in sorted(FORBIDDEN_CLASSES):
            fixture = website_index.replace(
                "<body>",
                f'<body class="{class_name}">',
                1,
            )
            with self.subTest(forbidden=class_name):
                self.assertIn(
                    f"forbidden-class:{class_name}",
                    document_contract_errors(
                        "website/index.html",
                        fixture,
                    ),
                )

        invalid_cases = {
            "measure-missing": (
                "shop/index.html",
                shop_index.replace(
                    " u-measure-860",
                    "",
                    1,
                ),
            ),
            "component-root-missing": (
                "website/index.html",
                website_index.replace(
                    'class="c-card c-card--lg"',
                    'class="removed-card c-card--lg"',
                    1,
                ),
            ),
            "text-changed": (
                "website/index.html",
                website_index.replace(
                    "主力サービス",
                    "変更されたサービス",
                    1,
                ),
            ),
            "href-changed": (
                "website/index.html",
                website_index.replace(
                    'href="./index.html"',
                    'href="./changed.html"',
                    1,
                ),
            ),
            "id-changed": (
                "website/index.html",
                website_index.replace(
                    'id="top"',
                    'id="changed-top"',
                    1,
                ),
            ),
            "order-changed": (
                "website/index.html",
                swap_first_two_cards(website_index),
            ),
            "unrelated-class-removed": (
                "website/index.html",
                website_index.replace(
                    "c-card c-card--lg",
                    "c-card",
                    1,
                ),
            ),
        }
        for name, (path, fixture) in invalid_cases.items():
            with self.subTest(name=name):
                self.assertTrue(
                    document_contract_errors(path, fixture),
                    name,
                )

    def test_starter_owns_replacement_and_component_contracts(
        self,
    ) -> None:
        scss_sources = {
            path.relative_to(STARTER_ROOT).as_posix(): (
                path.read_text(encoding="utf-8")
            )
            for path in sorted(
                (STARTER_ROOT / "src/scss").rglob("*.scss")
            )
        }
        compiled_css = (
            STARTER_ROOT / "dist/css/main.css"
        ).read_text(encoding="utf-8")
        doc_paths = [
            *sorted(
                (STARTER_ROOT / "docs/components").rglob(
                    "*.md"
                )
            ),
            *sorted(
                (STARTER_ROOT / "docs/patterns").rglob(
                    "*.md"
                )
            ),
            STARTER_ROOT / "docs/architecture.md",
        ]
        docs = {
            path.relative_to(STARTER_ROOT).as_posix(): (
                path.read_text(encoding="utf-8")
            )
            for path in doc_paths
        }

        for class_name in sorted(FORBIDDEN_CLASSES):
            with self.subTest(class_name=class_name):
                self.assertFalse(
                    any(
                        token_occurs(source, class_name)
                        for source in scss_sources.values()
                    )
                )
                self.assertFalse(
                    token_occurs(compiled_css, class_name)
                )
                self.assertFalse(
                    any(
                        token_occurs(source, class_name)
                        for source in docs.values()
                    )
                )

        canonical_occurrences = {
            class_name: []
            for class_name in FORBIDDEN_CLASSES
        }
        for path in sorted(
            (STARTER_ROOT / "src/html").rglob("*.html")
        ):
            source = path.read_text(encoding="utf-8")
            for class_name in FORBIDDEN_CLASSES:
                if token_occurs(source, class_name):
                    canonical_occurrences[class_name].append(
                        path.relative_to(STARTER_ROOT).as_posix()
                    )
        self.assertEqual(
            {
                "c-card--fill": [],
                "flow-list--arrow": [],
                "flow-list__title-text": [
                    "src/html/arch-corp-index.html"
                ],
                "site-header--scroll-light": [],
                "u-measure-840": [],
            },
            canonical_occurrences,
        )

        measure_scss = scss_sources[
            "src/scss/utilities/_measure.scss"
        ]
        measure_scss_bodies = rule_bodies(
            measure_scss,
            ".u-measure-860",
        )
        measure_css_bodies = rule_bodies(
            compiled_css,
            ".u-measure-860",
        )
        for bodies in (
            measure_scss_bodies,
            measure_css_bodies,
        ):
            self.assertTrue(
                has_declaration(
                    bodies,
                    "inline-size",
                    "100%",
                )
            )
            self.assertTrue(
                has_declaration(
                    bodies,
                    "margin-inline",
                    "auto",
                )
            )
            self.assertTrue(
                has_declaration(
                    bodies,
                    "max-inline-size",
                    "860px",
                )
            )

        grid_scss = scss_sources[
            "src/scss/layouts/_grid.scss"
        ]
        for source in (grid_scss, compiled_css):
            uniform_bodies = rule_bodies(
                source,
                ".l-grid.l-grid--cards-uniform",
            )
            child_bodies = rule_bodies(
                source,
                ".l-grid.l-grid--cards-uniform > *",
            )
            self.assertTrue(
                has_declaration(
                    uniform_bodies,
                    "grid-auto-rows",
                    "1fr",
                )
            )
            self.assertTrue(
                has_declaration(
                    uniform_bodies,
                    "align-items",
                    "stretch",
                )
            )
            self.assertTrue(
                has_declaration(
                    child_bodies,
                    "block-size",
                    "100%",
                )
            )

        flow_scss = scss_sources[
            "src/scss/components/flow/_flow-base.scss"
        ]
        for selector in (
            ".flow-list",
            ".flow-list__item",
            ".flow-list__num",
            ".flow-list__body",
            ".flow-list__title",
            ".flow-list__text",
        ):
            self.assertTrue(
                rule_bodies(flow_scss, selector),
                selector,
            )
            self.assertTrue(
                rule_bodies(compiled_css, selector),
                selector,
            )
        self.assertTrue(
            has_declaration(
                rule_bodies(
                    flow_scss,
                    ".flow-list__item:not(:last-child)::after",
                ),
                "content",
                "'↓'",
            )
        )

        layout_docs = docs[
            "docs/components/layout-primitives.md"
        ]
        self.assertIn(
            "`.l-grid--cards-uniform`: 直接の子要素の高さをそろえる",
            layout_docs,
        )

    def test_generated_templates_preserve_class_and_prior_contracts(
        self,
    ) -> None:
        expected_actions = expectations_by_path()

        with tempfile.TemporaryDirectory(
            prefix="pg-html-006-"
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
                project_name = (
                    f"{template_name} Class Contract"
                )

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
                    self.assertEqual(
                        [],
                        document_contract_errors(
                            source_path,
                            text,
                            project_name=project_name,
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


if __name__ == "__main__":
    unittest.main()
