from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from textwrap import dedent
from uuid import uuid4

from generation_manifest import sha256_file, utc_timestamp

from filesystem_safety import rename_with_retry

from project_naming import (
    sanitize_project_slug,
    sanitize_theme_name,
)
from console_safety import configure_standard_streams


TEMPLATE_CONFIGS = {
    "website": {
        "html_to_php_map": {
            "index.html": "front-page.php",
            "about.html": "page-about.php",
            "service.html": "page-service.php",
            "contact.html": "page-contact.php",
        },
        "home_url_map": {
            "index.html": "<?php echo esc_url( home_url( '/' ) ); ?>",
            "about.html": "<?php echo esc_url( home_url( '/about/' ) ); ?>",
            "service.html": "<?php echo esc_url( home_url( '/service/' ) ); ?>",
            "contact.html": "<?php echo esc_url( home_url( '/contact/' ) ); ?>",
        },
    },
    "shop": {
        "html_to_php_map": {
            "index.html": "front-page.php",
            "products.html": "page-products.php",
            "about.html": "page-about.php",
            "contact.html": "page-contact.php",
        },
        "home_url_map": {
            "index.html": "<?php echo esc_url( home_url( '/' ) ); ?>",
            "products.html": "<?php echo esc_url( home_url( '/products/' ) ); ?>",
            "about.html": "<?php echo esc_url( home_url( '/about/' ) ); ?>",
            "contact.html": "<?php echo esc_url( home_url( '/contact/' ) ); ?>",
        },
    },
    "lp": {
        "html_to_php_map": {
            "index.html": "front-page.php",
        },
        "home_url_map": {
            "index.html": "<?php echo esc_url( home_url( '/' ) ); ?>",
            "contact.html": "<?php echo esc_url( home_url( '/#cta' ) ); ?>",
            "service.html": "<?php echo esc_url( home_url( '/#offer' ) ); ?>",
        },
    },
}
SUPPORTED_TEMPLATES = tuple(TEMPLATE_CONFIGS)
BASE_GENERATED_FILES = (
    "style.css",
    "index.php",
    "functions.php",
    "header.php",
    "footer.php",
)
ALL_GENERATED_FILES = tuple(
    dict.fromkeys(
        BASE_GENERATED_FILES
        + tuple(
            php_name
            for config in TEMPLATE_CONFIGS.values()
            for php_name in config["html_to_php_map"].values()
        )
    )
)

WP_OWNERSHIP_MANIFEST_FILENAME = (
    ".project-generator-wordpress.json"
)
WP_OWNERSHIP_MANIFEST_KIND = (
    "project-generator-wordpress-ownership"
)
GET_HEADER = "<?php get_header(); ?>"
GET_FOOTER = "<?php get_footer(); ?>"
WP_HEAD = "<?php wp_head(); ?>"
WP_FOOTER = "<?php wp_footer(); ?>"
WP_TITLE = "<?php echo esc_html( wp_get_document_title() ); ?>"
STYLESHEET_URI_PREFIX = "<?php echo esc_url( get_stylesheet_directory_uri() . '"
STYLESHEET_URI_SUFFIX = "' ); ?>"
FUNCTIONS_PHP_TEMPLATE = dedent(
    """\
    <?php
    function pg_asset_version( $relative_path ) {
      $file_path = get_stylesheet_directory() . $relative_path;
      if ( file_exists( $file_path ) ) {
        return (string) filemtime( $file_path );
      }

      return null;
    }

    function pg_enqueue_assets() {
      wp_enqueue_style(
        'pg-main',
        get_stylesheet_directory_uri() . '/dist/css/main.css',
        array(),
        pg_asset_version( '/dist/css/main.css' )
      );

      wp_enqueue_script(
        'pg-main',
        get_stylesheet_directory_uri() . '/dist/js/core/app.js',
        array(),
        pg_asset_version( '/dist/js/core/app.js' ),
        true
      );
    }
    add_action( 'wp_enqueue_scripts', 'pg_enqueue_assets' );

    function pg_add_module_attribute( $tag, $handle, $src ) {
      if ( 'pg-main' !== $handle ) {
        return $tag;
      }

      return sprintf(
        '<script type="module" src="%s"></script>',
        esc_url( $src )
      );
    }
    add_filter( 'script_loader_tag', 'pg_add_module_attribute', 10, 3 );
    """
)


class ConversionError(Exception):
    """Raised when a generated HTML file cannot be converted safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="project-generator の website 出力を最小構成の WordPress 風 PHP テンプレへ変換します。"
    )
    parser.add_argument(
        "-p",
        "--project",
        required=True,
        help="変換対象の案件名を指定します。outputs/<project-name>/ を読み込みます。",
    )
    parser.add_argument(
        "-t",
        "--template",
        default="website",
        choices=SUPPORTED_TEMPLATES,
        help="現在は website / shop / lp に対応しています。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存のgenerator管理WordPressファイルを置換します。",
    )
    return parser.parse_args()


def sanitize_project_name(project_name: str) -> str:
    try:
        return sanitize_project_slug(project_name)
    except ValueError as error:
        raise ConversionError(str(error)) from error


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def render_style_css(
    style_css_template: str,
    *,
    project_name: str,
) -> str:
    theme_name_pattern = re.compile(
        r"^(Theme Name:\s*).*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    safe_theme_name = sanitize_theme_name(project_name)

    if theme_name_pattern.search(style_css_template):
        return theme_name_pattern.sub(
            lambda match: (
                f"{match.group(1)}{safe_theme_name}"
            ),
            style_css_template,
            count=1,
        )

    return (
        "/*\n"
        f"Theme Name: {safe_theme_name}\n"
        "*/\n\n"
        f"{style_css_template.lstrip()}"
    )


def generate_wp_stub_files(*, base_dir: Path, project_dir: Path, project_name: str) -> list[str]:
    wp_stubs_dir = base_dir / "wp-stubs"
    style_stub_path = wp_stubs_dir / "style.css"
    index_stub_path = wp_stubs_dir / "index.php"

    if not style_stub_path.exists():
        raise ConversionError(f"`wp-stubs/style.css` が見つかりません: {style_stub_path}")
    if not index_stub_path.exists():
        raise ConversionError(f"`wp-stubs/index.php` が見つかりません: {index_stub_path}")

    rendered_style_css = render_style_css(
        read_text(style_stub_path),
        project_name=project_name,
    )
    write_text(project_dir / "style.css", rendered_style_css)
    shutil.copyfile(index_stub_path, project_dir / "index.php")

    return ["style.css", "index.php"]


def find_tag_block(text: str, tag_name: str, *, start: int = 0) -> tuple[int, int]:
    pattern = re.compile(rf"</?{tag_name}\b[^>]*>", flags=re.IGNORECASE)
    first_match = pattern.search(text, start)
    if not first_match or first_match.group(0).startswith("</"):
        raise ConversionError(f"`<{tag_name}>` が見つかりません。")

    depth = 1
    cursor = first_match.end()

    while depth > 0:
        match = pattern.search(text, cursor)
        if not match:
            raise ConversionError(f"`<{tag_name}>` の閉じタグが見つかりません。")

        token = match.group(0)
        if token.startswith("</"):
            depth -= 1
        elif not token.endswith("/>"):
            depth += 1
        cursor = match.end()

    return first_match.start(), cursor


def insert_before_closing_tag(text: str, closing_tag: str, snippet: str) -> str:
    pattern = re.compile(rf"(?im)^([ \t]*){re.escape(closing_tag)}")
    match = pattern.search(text)
    if not match:
        raise ConversionError(f"`{closing_tag}` が見つかりません。")

    indent = match.group(1)
    insertion = f"{indent}{snippet}\n"
    return text[: match.start()] + insertion + text[match.start() :]


def remove_asset_tag(text: str, *, tag_name: str, asset_fragment: str) -> str:
    pattern = re.compile(
        rf'^[ \t]*<{tag_name}\b(?=[^>]*{re.escape(asset_fragment)})[^>]*>(?:</{tag_name}>)?[ \t]*\n?',
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return pattern.sub("", text, count=1)


def remove_class_token(text: str, token: str) -> str:
    class_pattern = re.compile(r'class="([^"]*)"')

    def replacer(match: re.Match[str]) -> str:
        classes = [name for name in match.group(1).split() if name != token]
        if not classes:
            return ""
        return f'class="{" ".join(classes)}"'

    return class_pattern.sub(replacer, text)


def normalize_path(path: str) -> str:
    if path.startswith("./"):
        return path[2:]
    return path.lstrip("/")


def stylesheet_directory_uri_expr(path: str) -> str:
    normalized = normalize_path(path)
    return f"{STYLESHEET_URI_PREFIX}/{normalized}{STYLESHEET_URI_SUFFIX}"


def page_url_expr(path: str, *, home_url_map: dict[str, str]) -> str | None:
    normalized = normalize_path(path)
    return home_url_map.get(normalized)


def rewrite_site_title_link(text: str) -> str:
    pattern = re.compile(
        r'<a\b(?=[^>]*class="site-title__link")[^>]*>.*?</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    replacement = (
        '<a href="<?php echo esc_url( home_url( \'/\' ) ); ?>" class="site-title__link">'
        "<?php bloginfo( 'name' ); ?>"
        "</a>"
    )
    return pattern.sub(replacement, text, count=1)


def rewrite_href_and_src_paths(text: str, *, home_url_map: dict[str, str]) -> str:
    attr_pattern = re.compile(r'(?P<attr>\b(?:href|src)\s*=\s*")(?P<path>[^"]+)(")')

    def replacer(match: re.Match[str]) -> str:
        attr = match.group("attr")
        path = match.group("path")
        suffix = match.group(3)

        page_expr = page_url_expr(path, home_url_map=home_url_map)
        if page_expr is not None:
            return f"{attr}{page_expr}{suffix}"

        normalized = normalize_path(path)
        if normalized.startswith(("dist/css/", "dist/js/", "assets/img/", "img/")):
            return f'{attr}{stylesheet_directory_uri_expr(path)}{suffix}'

        return match.group(0)

    return attr_pattern.sub(replacer, text)


def wordpress_current_page_condition(
    path: str,
    *,
    home_url_map: dict[str, str],
) -> str | None:
    normalized = normalize_path(path)

    if normalized not in home_url_map:
        return None

    if normalized == "index.html":
        return "is_front_page()"

    slug = Path(normalized).stem

    if not re.fullmatch(
        r"[a-z0-9-]+",
        slug,
    ):
        return None

    return f"is_page( '{slug}' )"


def rewrite_navigation_current_state(
    text: str,
    *,
    home_url_map: dict[str, str],
) -> str:
    nav_pattern = re.compile(
        r"<nav\b[^>]*>.*?</nav>",
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    anchor_pattern = re.compile(
        r"<a\b[^>]*>",
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    href_pattern = re.compile(
        (
            r"\bhref\s*=\s*"
            r"(?P<quote>[\"'])"
            r"(?P<path>.*?)"
            r"(?P=quote)"
        ),
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    class_pattern = re.compile(
        (
            r"\bclass\s*=\s*"
            r"(?P<quote>[\"'])"
            r"(?P<classes>.*?)"
            r"(?P=quote)"
        ),
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    current_pattern = re.compile(
        (
            r"\s+aria-current\s*=\s*"
            r"(?P<quote>[\"'])"
            r"page"
            r"(?P=quote)"
        ),
        flags=re.IGNORECASE,
    )

    def rewrite_anchor(
        match: re.Match[str],
    ) -> str:
        anchor = match.group(0)
        href_match = href_pattern.search(
            anchor
        )

        if href_match is None:
            return anchor

        condition = (
            wordpress_current_page_condition(
                href_match.group("path"),
                home_url_map=home_url_map,
            )
        )

        if condition is None:
            return anchor

        anchor = current_pattern.sub(
            "",
            anchor,
        )

        class_match = class_pattern.search(
            anchor
        )

        if class_match is not None:
            class_tokens = [
                token
                for token
                in class_match.group(
                    "classes"
                ).split()
                if token != "is-current"
            ]
            static_classes = " ".join(
                class_tokens
            )
            active_value = (
                " is-current"
                if static_classes
                else "is-current"
            )
            dynamic_class = (
                'class="'
                + static_classes
                + "<?php echo "
                + condition
                + " ? '"
                + active_value
                + "' : ''; ?>"
                + '"'
            )

            anchor = (
                anchor[
                    :class_match.start()
                ]
                + dynamic_class
                + anchor[
                    class_match.end():
                ]
            )

            current_attribute = (
                "<?php if ( "
                + condition
                + ' ) : ?> aria-current="page"'
                + "<?php endif; ?>"
            )

            return (
                anchor[:-1]
                + current_attribute
                + ">"
            )

        current_attributes = (
            "<?php if ( "
            + condition
            + ' ) : ?> class="is-current"'
            + ' aria-current="page"'
            + "<?php endif; ?>"
        )

        return (
            anchor[:-1]
            + current_attributes
            + ">"
        )

    def rewrite_nav(
        match: re.Match[str],
    ) -> str:
        return anchor_pattern.sub(
            rewrite_anchor,
            match.group(0),
        )

    return nav_pattern.sub(
        rewrite_nav,
        text,
    )


def normalize_header_html(
    header_html: str,
    *,
    template_name: str,
    home_url_map: dict[str, str],
) -> str:
    header_html = remove_asset_tag(
        header_html,
        tag_name="link",
        asset_fragment=(
            "dist/css/main.css"
        ),
    )
    header_html = re.sub(
        r"<title>.*?</title>",
        f"<title>{WP_TITLE}</title>",
        header_html,
        count=1,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )
    header_html = re.sub(
        r"<body\b[^>]*>",
        (
            "<body "
            f"<?php body_class('t-{template_name}'); ?>"
            ">"
        ),
        header_html,
        count=1,
        flags=re.IGNORECASE,
    )
    header_html = rewrite_site_title_link(
        header_html
    )
    header_html = (
        rewrite_navigation_current_state(
            header_html,
            home_url_map=home_url_map,
        )
    )
    header_html = rewrite_href_and_src_paths(
        header_html,
        home_url_map=home_url_map,
    )

    return header_html


def normalize_footer_html(
    footer_html: str,
    *,
    home_url_map: dict[str, str],
) -> str:
    footer_html = remove_asset_tag(
        footer_html,
        tag_name="script",
        asset_fragment=(
            "dist/js/core/app.js"
        ),
    )
    footer_html = (
        rewrite_navigation_current_state(
            footer_html,
            home_url_map=home_url_map,
        )
    )

    return rewrite_href_and_src_paths(
        footer_html,
        home_url_map=home_url_map,
    )


def normalize_main_html(main_html: str, *, home_url_map: dict[str, str]) -> str:
    return rewrite_href_and_src_paths(main_html, home_url_map=home_url_map)


def ensure_wp_hooks(header_html: str, footer_html: str) -> tuple[str, str]:
    if WP_HEAD not in header_html:
        header_html = insert_before_closing_tag(header_html, "</head>", WP_HEAD)
    if WP_FOOTER not in footer_html:
        footer_html = insert_before_closing_tag(footer_html, "</body>", WP_FOOTER)
    return header_html, footer_html


def split_document(html: str) -> tuple[str, str, str]:
    body_match = re.search(r"<body\b[^>]*>", html, flags=re.IGNORECASE)
    if not body_match:
        raise ConversionError("`<body>` が見つかりません。")

    main_start, main_end = find_tag_block(html, "main", start=body_match.end())
    footer_start, _ = find_tag_block(html, "footer", start=main_end)

    header_html = html[:main_start].rstrip() + "\n"
    main_html = html[main_start:main_end].strip() + "\n"
    footer_html = html[footer_start:].lstrip()

    return header_html, main_html, footer_html


def page_class_for_html_name(html_name: str) -> str:
    page_stem = Path(html_name).stem
    return (
        "p-home"
        if page_stem == "index"
        else f"p-{page_stem}"
    )


def build_page_php(
    main_html: str,
    *,
    page_class: str,
) -> str:
    body_class_filter = dedent(
        f"""\
        <?php
        add_filter(
          'body_class',
          static function ( $classes ) {{
            $classes[] = '{page_class}';
            return $classes;
          }}
        );
        ?>
        """
    ).strip()

    return (
        f"{body_class_filter}\n"
        f"{GET_HEADER}\n\n"
        f"{main_html.strip()}\n\n"
        f"{GET_FOOTER}\n"
    )


def build_functions_php() -> str:
    return FUNCTIONS_PHP_TEMPLATE


def ownership_manifest_path(
    project_dir: Path,
) -> Path:
    return (
        project_dir
        / WP_OWNERSHIP_MANIFEST_FILENAME
    )


def normalize_owned_generated_path(
    raw_path: object,
) -> str:
    if (
        not isinstance(raw_path, str)
        or not raw_path.strip()
    ):
        raise ConversionError(
            "WordPress所有権manifestの"
            "pathが不正です。"
        )

    normalized = (
        raw_path.strip()
        .replace("\\", "/")
    )
    path = PurePosixPath(
        normalized
    )

    if (
        path.is_absolute()
        or len(path.parts) != 1
        or path.parts[0]
        in {"", ".", ".."}
        or normalized
        not in ALL_GENERATED_FILES
    ):
        raise ConversionError(
            "WordPress所有権manifestの"
            "pathがgenerator管理範囲外です: "
            f"{normalized}"
        )

    return normalized


def is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(
            character
            in "0123456789abcdef"
            for character in value
        )
    )


def read_wordpress_ownership_manifest(
    project_dir: Path,
) -> dict | None:
    manifest_path = (
        ownership_manifest_path(
            project_dir
        )
    )

    if not manifest_path.exists():
        return None

    if not manifest_path.is_file():
        raise ConversionError(
            "WordPress所有権manifestが"
            "ファイルではありません: "
            f"{manifest_path}"
        )

    try:
        data = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise ConversionError(
            "WordPress所有権manifestを"
            f"読み込めません: {error}"
        ) from error

    if not isinstance(data, dict):
        raise ConversionError(
            "WordPress所有権manifestの"
            "ルートはobjectである必要が"
            "あります。"
        )

    if data.get("schemaVersion") != 1:
        raise ConversionError(
            "未対応のWordPress所有権"
            "manifest schemaVersionです。"
        )

    if (
        data.get("kind")
        != WP_OWNERSHIP_MANIFEST_KIND
    ):
        raise ConversionError(
            "WordPress所有権manifestの"
            "kindが不正です。"
        )

    template_name = data.get(
        "template"
    )

    if (
        not isinstance(template_name, str)
        or template_name
        not in SUPPORTED_TEMPLATES
    ):
        raise ConversionError(
            "WordPress所有権manifestの"
            "templateが不正です。"
        )

    raw_records = data.get(
        "generatedFiles"
    )

    if not isinstance(
        raw_records,
        list,
    ):
        raise ConversionError(
            "WordPress所有権manifestの"
            "generatedFilesは配列である"
            "必要があります。"
        )

    normalized_records = []
    seen_paths: set[str] = set()

    for raw_record in raw_records:
        if not isinstance(
            raw_record,
            dict,
        ):
            raise ConversionError(
                "WordPress所有権manifestの"
                "generatedFiles要素が"
                "不正です。"
            )

        path = (
            normalize_owned_generated_path(
                raw_record.get("path")
            )
        )
        file_hash = raw_record.get(
            "sha256"
        )

        if not is_sha256(file_hash):
            raise ConversionError(
                "WordPress所有権manifestの"
                f"SHA-256が不正です: {path}"
            )

        if path in seen_paths:
            raise ConversionError(
                "WordPress所有権manifestに"
                f"重複pathがあります: {path}"
            )

        seen_paths.add(path)
        normalized_records.append(
            {
                "path": path,
                "sha256": file_hash,
            }
        )

    return {
        "schemaVersion": 1,
        "kind": (
            WP_OWNERSHIP_MANIFEST_KIND
        ),
        "template": template_name,
        "generatedFiles": (
            normalized_records
        ),
    }


def find_existing_generated_files(
    project_dir: Path,
) -> list[str]:
    return [
        name
        for name in ALL_GENERATED_FILES
        if (project_dir / name).exists()
    ]


def validate_wordpress_ownership(
    project_dir: Path,
    ownership_manifest: dict,
) -> list[str]:
    records = (
        ownership_manifest[
            "generatedFiles"
        ]
    )

    owned_hashes = {
        record["path"]: record["sha256"]
        for record in records
    }

    existing_files = (
        find_existing_generated_files(
            project_dir
        )
    )

    untracked_files = sorted(
        set(existing_files)
        - set(owned_hashes)
    )

    if untracked_files:
        raise ConversionError(
            "generator所有権を確認できない"
            "WordPressファイルがあります。"
            "`--force`でも上書き・削除"
            "できません: "
            + ", ".join(untracked_files)
        )

    for path, expected_hash in (
        owned_hashes.items()
    ):
        file_path = project_dir / path

        if not file_path.exists():
            continue

        if not file_path.is_file():
            raise ConversionError(
                "generator所有ファイルと"
                "同名のディレクトリが"
                f"あります: {file_path}"
            )

        actual_hash = sha256_file(
            file_path
        )

        if actual_hash != expected_hash:
            raise ConversionError(
                "generator生成後に変更された"
                "WordPressファイルがあります。"
                "`--force`でも上書き・削除"
                "できません。"
                f" path={path}"
                f" expected={expected_hash}"
                f" actual={actual_hash}"
            )

    return sorted(
        owned_hashes
    )


def remove_generated_files(
    project_dir: Path,
    owned_files: list[str],
) -> None:
    for name in owned_files:
        normalized = (
            normalize_owned_generated_path(
                name
            )
        )
        path = project_dir / normalized

        if not path.exists():
            continue

        if not path.is_file():
            raise ConversionError(
                "generator所有ファイルと"
                "同名のディレクトリが"
                f"あります: {path}"
            )

        path.unlink()

    manifest_path = (
        ownership_manifest_path(
            project_dir
        )
    )

    if manifest_path.exists():
        if not manifest_path.is_file():
            raise ConversionError(
                "WordPress所有権manifestと"
                "同名のディレクトリが"
                f"あります: {manifest_path}"
            )

        manifest_path.unlink()


def build_wordpress_ownership_records(
    project_dir: Path,
    generated_files: list[str],
) -> list[dict[str, str]]:
    normalized_files = sorted(
        dict.fromkeys(
            normalize_owned_generated_path(
                name
            )
            for name in generated_files
        )
    )

    records = []

    for name in normalized_files:
        path = project_dir / name

        if not path.is_file():
            raise ConversionError(
                "所有権manifestへ記録する"
                "生成ファイルがありません: "
                f"{path}"
            )

        records.append(
            {
                "path": name,
                "sha256": sha256_file(
                    path
                ),
            }
        )

    return records


def write_wordpress_ownership_manifest(
    *,
    project_dir: Path,
    template_name: str,
    generated_files: list[str],
) -> dict:
    manifest = {
        "schemaVersion": 1,
        "kind": (
            WP_OWNERSHIP_MANIFEST_KIND
        ),
        "template": template_name,
        "updatedAt": utc_timestamp(),
        "generatedFiles": (
            build_wordpress_ownership_records(
                project_dir,
                generated_files,
            )
        ),
    }

    ownership_manifest_path(
        project_dir
    ).write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return manifest


def replace_directory_transactionally(
    staging_dir: Path,
    destination_dir: Path,
) -> None:
    backup_dir = destination_dir.parent / (
        f".{destination_dir.name}.wp-backup-{uuid4().hex}"
    )

    rename_with_retry(destination_dir, backup_dir)

    try:
        rename_with_retry(staging_dir, destination_dir)
    except Exception:
        if backup_dir.exists() and not destination_dir.exists():
            rename_with_retry(backup_dir, destination_dir)
        raise
    else:
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def generate_wordpress_files(
    *,
    base_dir: Path,
    project_dir: Path,
    project_name: str,
    template_name: str,
) -> list[str]:
    config = TEMPLATE_CONFIGS[template_name]
    html_to_php_map = config["html_to_php_map"]
    home_url_map = config["home_url_map"]

    header_html, _, footer_html = split_document(
        read_text(project_dir / "index.html")
    )
    header_html = normalize_header_html(
        header_html,
        template_name=template_name,
        home_url_map=home_url_map,
    )
    footer_html = normalize_footer_html(
        footer_html,
        home_url_map=home_url_map,
    )
    header_html, footer_html = ensure_wp_hooks(
        header_html,
        footer_html,
    )

    write_text(
        project_dir / "functions.php",
        build_functions_php(),
    )
    write_text(
        project_dir / "header.php",
        header_html,
    )
    write_text(
        project_dir / "footer.php",
        footer_html,
    )

    generated_files = generate_wp_stub_files(
        base_dir=base_dir,
        project_dir=project_dir,
        project_name=project_name,
    )
    generated_files.extend(
        [
            "functions.php",
            "header.php",
            "footer.php",
        ]
    )

    for html_name, php_name in html_to_php_map.items():
        _, main_html, _ = split_document(
            read_text(project_dir / html_name)
        )
        main_html = normalize_main_html(
            main_html,
            home_url_map=home_url_map,
        )
        write_text(
            project_dir / php_name,
            build_page_php(
                main_html,
                page_class=page_class_for_html_name(
                    html_name
                ),
            ),
        )
        generated_files.append(php_name)

    return generated_files


def convert_project(
    *,
    base_dir: Path,
    project_name: str,
    template_name: str,
    force: bool = False,
) -> tuple[Path, list[str]]:
    if template_name not in TEMPLATE_CONFIGS:
        raise ConversionError(
            "現在は `website` `shop` `lp` "
            "テンプレのみ変換できます。"
        )

    config = TEMPLATE_CONFIGS[
        template_name
    ]
    html_to_php_map = config[
        "html_to_php_map"
    ]

    project_dir = (
        base_dir
        / "outputs"
        / sanitize_project_name(
            project_name
        )
    )

    if (
        not project_dir.exists()
        or not project_dir.is_dir()
    ):
        raise ConversionError(
            "対象案件フォルダが"
            f"見つかりません: {project_dir}"
        )

    missing_files = [
        name
        for name in html_to_php_map
        if not (
            project_dir
            / name
        ).is_file()
    ]

    if missing_files:
        joined = ", ".join(
            missing_files
        )
        raise ConversionError(
            "必要な HTML が不足しています: "
            f"{joined}"
        )

    existing_files = (
        find_existing_generated_files(
            project_dir
        )
    )
    ownership_manifest = (
        read_wordpress_ownership_manifest(
            project_dir
        )
    )

    conversion_exists = bool(
        existing_files
        or ownership_manifest is not None
    )

    if conversion_exists and not force:
        joined = (
            ", ".join(existing_files)
            if existing_files
            else (
                WP_OWNERSHIP_MANIFEST_FILENAME
            )
        )

        raise ConversionError(
            "WordPress変換済み、または"
            "generator管理名のファイルが"
            f"既に存在します: {joined}。"
            "再変換する場合は `--force` を"
            "指定してください。"
        )

    owned_files: list[str] = []

    if force and conversion_exists:
        if ownership_manifest is None:
            raise ConversionError(
                "既存WordPressファイルの"
                "generator所有権を確認できる"
                "manifestがありません。"
                "`--force`でも上書き・削除"
                "できません: "
                + ", ".join(
                    existing_files
                )
            )

        owned_files = (
            validate_wordpress_ownership(
                project_dir,
                ownership_manifest,
            )
        )

    staging_dir = (
        project_dir.parent
        / (
            f".{project_dir.name}"
            f".wp-tmp-{uuid4().hex}"
        )
    )

    try:
        shutil.copytree(
            project_dir,
            staging_dir,
        )

        remove_generated_files(
            staging_dir,
            owned_files,
        )

        generated_files = (
            generate_wordpress_files(
                base_dir=base_dir,
                project_dir=staging_dir,
                project_name=project_name,
                template_name=template_name,
            )
        )

        write_wordpress_ownership_manifest(
            project_dir=staging_dir,
            template_name=template_name,
            generated_files=generated_files,
        )

        replace_directory_transactionally(
            staging_dir,
            project_dir,
        )
    finally:
        if staging_dir.exists():
            shutil.rmtree(
                staging_dir,
                ignore_errors=True,
            )

    return project_dir, generated_files


def main() -> None:
    configure_standard_streams()
    args = parse_args()
    base_dir = Path(__file__).resolve().parent

    try:
        project_dir, generated_files = convert_project(
            base_dir=base_dir,
            project_name=args.project,
            template_name=args.template,
            force=args.force,
        )
    except (ConversionError, OSError) as error:
        print(error)
        raise SystemExit(1) from error

    print(f"\nPHP 変換完了: {project_dir}")
    for name in generated_files:
        print(f"- {name}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n処理を中断しました。")
        sys.exit(1)
