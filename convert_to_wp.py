from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from textwrap import dedent


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
    return parser.parse_args()


def sanitize_project_name(project_name: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*]+', "-", project_name.strip())
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    normalized = normalized.strip(" .-_")
    if not normalized:
        raise ConversionError("案件名から有効なフォルダ名を作成できませんでした。")
    return normalized


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def render_style_css(style_css_template: str, *, project_name: str) -> str:
    theme_name_pattern = re.compile(r"^(Theme Name:\s*).*$", flags=re.IGNORECASE | re.MULTILINE)
    replacement = rf"\1{project_name}"

    if theme_name_pattern.search(style_css_template):
        return theme_name_pattern.sub(replacement, style_css_template, count=1)

    return f"/*\nTheme Name: {project_name}\n*/\n\n{style_css_template.lstrip()}"


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


def normalize_header_html(
    header_html: str,
    *,
    template_name: str,
    home_url_map: dict[str, str],
) -> str:
    header_html = remove_asset_tag(
        header_html,
        tag_name="link",
        asset_fragment="dist/css/main.css",
    )
    header_html = re.sub(
        r"<title>.*?</title>",
        f"<title>{WP_TITLE}</title>",
        header_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    header_html = re.sub(
        r"<body\b[^>]*>",
        f"<body <?php body_class('t-{template_name}'); ?>>",
        header_html,
        count=1,
        flags=re.IGNORECASE,
    )
    header_html = re.sub(r'\s+aria-current="page"', "", header_html, flags=re.IGNORECASE)
    header_html = remove_class_token(header_html, "is-current")
    header_html = re.sub(r"(<a\b[^>]*?)\s+>", r"\1>", header_html, flags=re.IGNORECASE)
    header_html = rewrite_site_title_link(header_html)
    header_html = rewrite_href_and_src_paths(header_html, home_url_map=home_url_map)
    return header_html


def normalize_footer_html(footer_html: str, *, home_url_map: dict[str, str]) -> str:
    footer_html = remove_asset_tag(
        footer_html,
        tag_name="script",
        asset_fragment="dist/js/core/app.js",
    )
    return rewrite_href_and_src_paths(footer_html, home_url_map=home_url_map)


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


def build_page_php(main_html: str) -> str:
    return f"{GET_HEADER}\n\n{main_html.strip()}\n\n{GET_FOOTER}\n"


def build_functions_php() -> str:
    return FUNCTIONS_PHP_TEMPLATE


def convert_project(*, base_dir: Path, project_name: str, template_name: str) -> tuple[Path, list[str]]:
    if template_name not in TEMPLATE_CONFIGS:
        raise ConversionError("現在は `website` `shop` `lp` テンプレのみ変換できます。")

    config = TEMPLATE_CONFIGS[template_name]
    html_to_php_map = config["html_to_php_map"]
    home_url_map = config["home_url_map"]

    project_dir = base_dir / "outputs" / sanitize_project_name(project_name)
    if not project_dir.exists() or not project_dir.is_dir():
        raise ConversionError(f"対象案件フォルダが見つかりません: {project_dir}")

    missing_files = [name for name in html_to_php_map if not (project_dir / name).exists()]
    if missing_files:
        joined = ", ".join(missing_files)
        raise ConversionError(f"必要な HTML が不足しています: {joined}")

    header_html, _, footer_html = split_document(read_text(project_dir / "index.html"))
    header_html = normalize_header_html(
        header_html,
        template_name=template_name,
        home_url_map=home_url_map,
    )
    footer_html = normalize_footer_html(footer_html, home_url_map=home_url_map)
    header_html, footer_html = ensure_wp_hooks(header_html, footer_html)

    write_text(project_dir / "functions.php", build_functions_php())
    write_text(project_dir / "header.php", header_html)
    write_text(project_dir / "footer.php", footer_html)

    generated_files = generate_wp_stub_files(
        base_dir=base_dir,
        project_dir=project_dir,
        project_name=project_name,
    )
    generated_files.extend(["functions.php", "header.php", "footer.php"])

    for html_name, php_name in html_to_php_map.items():
        _, main_html, _ = split_document(read_text(project_dir / html_name))
        main_html = normalize_main_html(main_html, home_url_map=home_url_map)
        write_text(project_dir / php_name, build_page_php(main_html))
        generated_files.append(php_name)

    return project_dir, generated_files


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent

    try:
        project_dir, generated_files = convert_project(
            base_dir=base_dir,
            project_name=args.project,
            template_name=args.template,
        )
    except ConversionError as error:
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
