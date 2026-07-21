from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4


CSS_HREF = "./dist/css/main.css"
APP_JS_SRC = "./dist/js/core/app.js"
TEMPLATE_ORDER = ("website", "lp", "shop")
REQUIRED_DIST_FILES = (
    Path("css/main.css"),
    Path("js/core/app.js"),
)
PAGE_TITLES = {
    "website": {
        "index": "トップページ",
        "about": "会社案内",
        "service": "サービス",
        "contact": "お問い合わせ",
    },
    "lp": {
        "index": "ランディングページ",
    },
    "shop": {
        "index": "ショップトップ",
        "products": "商品一覧",
        "about": "店舗紹介",
        "contact": "お問い合わせ",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="project-generator: 仕事用スターターテンプレを outputs/ に生成します。"
    )
    parser.add_argument(
        "-t",
        "--template",
        choices=TEMPLATE_ORDER,
        help="生成するテンプレ種別を指定します。",
    )
    parser.add_argument(
        "-p",
        "--project",
        help="案件名を指定します。未指定時は対話入力します。",
    )
    parser.add_argument(
        "-r",
        "--refresh-dist",
        action="store_true",
        help="既存案件の dist/css と dist/js のみを再コピーします。",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="同名の出力先がある場合に上書きします。",
    )
    return parser.parse_args()


def prompt_template() -> str:
    while True:
        print("\nテンプレを選択してください。")
        for index, name in enumerate(TEMPLATE_ORDER, start=1):
            print(f"{index}: {name}")

        choice = input("> ").strip()
        if choice.isdigit():
            selected = int(choice) - 1
            if 0 <= selected < len(TEMPLATE_ORDER):
                return TEMPLATE_ORDER[selected]

        if choice in TEMPLATE_ORDER:
            return choice

        print("`website` `lp` `shop` のいずれかを選択してください。")


def prompt_project_name() -> str:
    while True:
        project = input("\n案件名を入力してください。\n> ").strip()
        if project:
            return project
        print("案件名は空欄にできません。")


def sanitize_project_name(project_name: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*]+', "-", project_name.strip())
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    normalized = normalized.strip(" .-_")
    if not normalized:
        raise ValueError("案件名から有効なフォルダ名を作成できませんでした。")
    return normalized


def confirm_overwrite(output_dir: Path) -> bool:
    while True:
        answer = (
            input(f"\n{output_dir.name} はすでに存在します。上書きしますか？ (y/n)\n> ")
            .strip()
            .lower()
        )
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def page_title_for(template_name: str, html_path: Path) -> str:
    page_key = html_path.stem
    return PAGE_TITLES.get(template_name, {}).get(page_key, page_key.title())


def replace_placeholders(
    html_path: Path,
    *,
    project_name: str,
    generated_date: str,
    page_title: str,
) -> None:
    replacements = {
        "{{PROJECT}}": project_name,
        "{{DATE}}": generated_date,
        "{{PAGE_TITLE}}": page_title,
    }

    text = read_text(html_path)
    for old, new in replacements.items():
        text = text.replace(old, new)
    write_text(html_path, text)


def inject_body_classes(html_path: Path, template_name: str) -> None:
    page_class = "p-home" if html_path.stem == "index" else f"p-{html_path.stem}"
    required_classes = [f"t-{template_name}", page_class]

    text = read_text(html_path)
    match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if not match:
        return

    body_tag = match.group(0)
    class_match = re.search(r'class\s*=\s*"([^"]*)"', body_tag, flags=re.IGNORECASE)

    if class_match:
        classes = class_match.group(1).split()
        for name in required_classes:
            if name not in classes:
                classes.append(name)
        new_body_tag = re.sub(
            r'class\s*=\s*"([^"]*)"',
            f'class="{" ".join(classes)}"',
            body_tag,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        new_body_tag = body_tag[:-1] + f' class="{" ".join(required_classes)}">'

    write_text(html_path, text.replace(body_tag, new_body_tag, 1))


def normalize_css_link(html_path: Path) -> None:
    text = read_text(html_path)
    main_css_pattern = re.compile(
        r"<link\b(?=[^>]*rel\s*=\s*['\"]stylesheet['\"])(?=[^>]*href\s*=\s*['\"][^'\"]*main\.css[^'\"]*['\"])[^>]*>",
        flags=re.IGNORECASE,
    )

    if main_css_pattern.search(text):
        updated = main_css_pattern.sub(
            f'<link rel="stylesheet" href="{CSS_HREF}" />',
            text,
            count=1,
        )
        write_text(html_path, updated)
        return

    if "</head>" in text:
        updated = text.replace(
            "</head>",
            f'  <link rel="stylesheet" href="{CSS_HREF}" />\n</head>',
            1,
        )
        write_text(html_path, updated)


def normalize_main_tag(html_path: Path) -> None:
    text = read_text(html_path)
    match = re.search(r"<main\b[^>]*>", text, flags=re.IGNORECASE)
    if not match:
        return

    main_tag = match.group(0)
    class_match = re.search(r'class\s*=\s*"([^"]*)"', main_tag, flags=re.IGNORECASE)

    if class_match:
        classes = class_match.group(1).split()
        if "main" not in classes:
            classes.insert(0, "main")
        new_main_tag = re.sub(
            r'class\s*=\s*"([^"]*)"',
            f'class="{" ".join(classes)}"',
            main_tag,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        new_main_tag = main_tag[:-1] + ' class="main">'

    write_text(html_path, text.replace(main_tag, new_main_tag, 1))


def normalize_app_script(html_path: Path) -> None:
    text = read_text(html_path)
    script_pattern = re.compile(
        r"<script\b(?=[^>]*src\s*=\s*['\"][^'\"]*app\.js[^'\"]*['\"])[^>]*></script>",
        flags=re.IGNORECASE,
    )

    if script_pattern.search(text):
        updated = script_pattern.sub(
            f'<script type="module" src="{APP_JS_SRC}"></script>',
            text,
            count=1,
        )
        write_text(html_path, updated)
        return

    if "</body>" in text:
        updated = text.replace(
            "</body>",
            f'  <script type="module" src="{APP_JS_SRC}"></script>\n</body>',
            1,
        )
        write_text(html_path, updated)


def normalize_html(html_path: Path) -> None:
    normalize_css_link(html_path)
    normalize_main_tag(html_path)
    normalize_app_script(html_path)


def ensure_output_structure(output_dir: Path) -> None:
    (output_dir / "assets" / "img").mkdir(parents=True, exist_ok=True)
    (output_dir / "dist").mkdir(parents=True, exist_ok=True)


def resolve_exiga_dist(base_dir: Path) -> Path:
    dist_root = base_dir.parent / "sass-starter-exiga" / "dist"
    if not dist_root.exists() or not dist_root.is_dir():
        raise FileNotFoundError(
            f"`sass-starter-exiga/dist` が見つかりません: {dist_root}"
        )

    for relative_path in REQUIRED_DIST_FILES:
        source = dist_root / relative_path
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(
                f"必須distファイルが見つかりません: {source}"
            )

    return dist_root


def copy_exiga_dist(dist_root: Path, destination_dist_dir: Path) -> None:
    destination_dist_dir.mkdir(parents=True, exist_ok=True)

    for directory_name in ("css", "js"):
        source = dist_root / directory_name
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(
                f"`dist/{directory_name}` が見つかりません: {source}"
            )

        destination = destination_dist_dir / directory_name
        shutil.copytree(source, destination)


def replace_directory_transactionally(
    staging_dir: Path,
    destination_dir: Path,
) -> None:
    if destination_dir.exists() and not destination_dir.is_dir():
        raise FileExistsError(
            f"置換対象がディレクトリではありません: {destination_dir}"
        )

    backup_dir = destination_dir.parent / (
        f".{destination_dir.name}.backup-{uuid4().hex}"
    )
    had_destination = destination_dir.exists()

    if had_destination:
        destination_dir.rename(backup_dir)

    try:
        staging_dir.rename(destination_dir)
    except Exception:
        if had_destination and backup_dir.exists() and not destination_dir.exists():
            backup_dir.rename(destination_dir)
        raise
    else:
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def refresh_dist(*, base_dir: Path, project_name: str) -> Path:
    outputs_dir = base_dir / "outputs"
    output_dir = outputs_dir / sanitize_project_name(project_name)

    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"対象案件フォルダが見つかりません: {output_dir}")

    dist_root = resolve_exiga_dist(base_dir)
    staging_dir = output_dir / f".dist.tmp-{uuid4().hex}"

    try:
        copy_exiga_dist(dist_root, staging_dir)
        replace_directory_transactionally(
            staging_dir,
            output_dir / "dist",
        )
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return output_dir


def prepare_html_files(
    output_dir: Path,
    *,
    template_name: str,
    project_name: str,
    generated_date: str,
) -> None:
    for html_path in sorted(output_dir.rglob("*.html")):
        replace_placeholders(
            html_path,
            project_name=project_name,
            generated_date=generated_date,
            page_title=page_title_for(template_name, html_path),
        )
        inject_body_classes(html_path, template_name)
        normalize_html(html_path)


def create_project(
    *,
    base_dir: Path,
    template_name: str,
    project_name: str,
    force: bool,
) -> Path:
    template_dir = base_dir / "templates" / template_name
    if not template_dir.exists() or not template_dir.is_dir():
        raise FileNotFoundError(f"テンプレが見つかりません: {template_dir}")

    dist_root = resolve_exiga_dist(base_dir)
    outputs_dir = base_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    output_dir = outputs_dir / sanitize_project_name(project_name)
    if output_dir.exists() and not output_dir.is_dir():
        raise FileExistsError(
            f"同名の出力先がディレクトリではありません: {output_dir}"
        )

    if output_dir.exists() and not force and not confirm_overwrite(output_dir):
        raise SystemExit("生成を中止しました。")

    staging_dir = outputs_dir / f".{output_dir.name}.tmp-{uuid4().hex}"

    try:
        shutil.copytree(template_dir, staging_dir)
        ensure_output_structure(staging_dir)

        generated_date = date.today().isoformat()
        prepare_html_files(
            staging_dir,
            template_name=template_name,
            project_name=project_name,
            generated_date=generated_date,
        )
        copy_exiga_dist(dist_root, staging_dir / "dist")
        replace_directory_transactionally(staging_dir, output_dir)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return output_dir


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parent

    if args.refresh_dist:
        if not args.project:
            print("`--refresh-dist` を使う場合は `--project` を指定してください。")
            raise SystemExit(1)

        try:
            output_dir = refresh_dist(base_dir=base_dir, project_name=args.project)
        except (OSError, ValueError) as error:
            print(error)
            raise SystemExit(1) from error

        print(f"\ndist 更新完了: {output_dir}")
        return

    template_name = args.template or prompt_template()
    project_name = args.project or prompt_project_name()

    try:
        output_dir = create_project(
            base_dir=base_dir,
            template_name=template_name,
            project_name=project_name,
            force=args.force,
        )
    except (OSError, ValueError) as error:
        print(error)
        raise SystemExit(1) from error

    print(f"\n生成完了: {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n処理を中断しました。")
        sys.exit(1)
