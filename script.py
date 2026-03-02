from pathlib import Path
from datetime import datetime
import shutil
import re


# -----------------------------
# 文字列置換（HTML用）
# -----------------------------
def replace_in_file(path: Path, replacements: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


# -----------------------------
# body クラス自動挿入
# t-<template> + p-<page>
# -----------------------------
def inject_body_classes(html_path: Path, template: str) -> None:
    page = html_path.stem
    page_class = "p-home" if page == "index" else f"p-{page}"
    template_class = f"t-{template}"
    add_classes = f"{template_class} {page_class}"

    text = html_path.read_text(encoding="utf-8")

    match = re.search(r"<body\b[^>]*>", text, flags=re.IGNORECASE)
    if not match:
        return

    body_tag = match.group(0)
    class_match = re.search(r'class\s*=\s*"([^"]*)"', body_tag, flags=re.IGNORECASE)

    if class_match:
        existing = class_match.group(1).strip()
        existing_set = set(existing.split())

        for c in add_classes.split():
            if c not in existing_set:
                existing += (" " if existing else "") + c

        new_body_tag = re.sub(
            r'class\s*=\s*"([^"]*)"',
            f'class="{existing}"',
            body_tag,
            flags=re.IGNORECASE,
        )
    else:
        new_body_tag = body_tag[:-1] + f' class="{add_classes}">'

    text = text.replace(body_tag, new_body_tag, 1)
    html_path.write_text(text, encoding="utf-8")


# =============================
# generator 側の出力規約（※新規生成時のみ使用）
# =============================
CSS_HREF = "./dist/css/main.css"


def normalize_css_link(html_path: Path) -> None:
    text = html_path.read_text(encoding="utf-8")

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        hm = re.search(r'href\s*=\s*"([^"]*)"', tag, flags=re.I)
        if not hm:
            return tag
        href = hm.group(1)
        # main.css だけ正規化（theme 等は触らない）
        if "main.css" not in href.lower():
            return tag
        return re.sub(
            r'href\s*=\s*"[^"]*"',
            f'href="{CSS_HREF}"',
            tag,
            flags=re.I,
        )

    text2 = re.sub(
        r"<link\b[^>]*rel\s*=\s*['\"]stylesheet['\"][^>]*>",
        repl,
        text,
        flags=re.I,
    )

    if text2 != text:
        html_path.write_text(text2, encoding="utf-8")


def normalize_main_tag(html_path: Path) -> None:
    text = html_path.read_text(encoding="utf-8")

    m = re.search(r"<main\b[^>]*>", text, flags=re.I)
    if not m:
        return

    main_tag = m.group(0)
    cm = re.search(r'class\s*=\s*"([^"]*)"', main_tag, flags=re.I)

    if cm:
        classes = [c for c in cm.group(1).split() if c != "container"]
        if "main" not in classes:
            classes.insert(0, "main")

        new_main_tag = re.sub(
            r'class\s*=\s*"([^"]*)"',
            f'class="{" ".join(classes)}"',
            main_tag,
            flags=re.I,
        )
    else:
        new_main_tag = main_tag[:-1] + ' class="main">'

    text2 = text.replace(main_tag, new_main_tag, 1)
    if text2 != text:
        html_path.write_text(text2, encoding="utf-8")


def normalize_html(html_path: Path) -> None:
    normalize_css_link(html_path)
    normalize_main_tag(html_path)


# -----------------------------
# exiga の CSS をコピー（dist/css を同期）
# -----------------------------
def copy_exiga_dist_to_output(output_dir: Path) -> None:
    base_dir = Path(__file__).parent
    exiga_dist_dir = base_dir.parent / "sass-starter-exiga" / "dist"

    if not exiga_dist_dir.exists():
        print("exiga の dist dir が見つかりません:", exiga_dist_dir)
        return

    # css / js を同期
    for sub in ("css", "js"):
        src = exiga_dist_dir / sub
        if not src.exists():
            print(f"exiga の dist/{sub} が見つかりません:", src)
            continue

        dst = output_dir / "dist" / sub
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)


# -----------------------------
# 既存の生成フォルダを選択（同期用）
# -----------------------------
def ask_existing_output_dir(base_dir: Path) -> Path | None:
    ignore = {"templates", "sass-starter-exiga", "__pycache__"}
    candidates = sorted(
        [
            p
            for p in base_dir.iterdir()
            if p.is_dir() and "_" in p.name and p.name not in ignore
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not candidates:
        print("既存の生成フォルダが見つかりません。")
        return None

    print("\n同期するフォルダを選んでください（CSSのみ）：")
    for i, p in enumerate(candidates, start=1):
        print(f"{i}: {p.name}")

    choice = input("> ").strip()
    if not choice.isdigit():
        return None

    idx = int(choice) - 1
    return candidates[idx] if 0 <= idx < len(candidates) else None


# -----------------------------
# テンプレ選択
# -----------------------------
def ask_template() -> str:
    base_dir = Path(__file__).parent
    templates_dir = base_dir / "templates"

    templates = sorted(
        p.name
        for p in templates_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )

    if not templates:
        raise SystemExit("テンプレが見つかりません")

    while True:
        print("\nテンプレを選択してください：")
        for i, name in enumerate(templates, start=1):
            print(f"{i}: {name}")

        choice = input("> ").strip()
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(templates):
                return templates[index]


# -----------------------------
# プロジェクト生成
# -----------------------------
def make_project(
    project: str,
    template: str,
    tel: str = "",
    tel_display: str = "",
) -> Path | None:
    today = datetime.now().strftime("%Y%m%d")

    base_dir = Path(__file__).parent
    template_dir = base_dir / "templates" / template
    output_dir = base_dir / f"{project}_{template}_{today}"

    if not template_dir.exists():
        print("テンプレが見つかりません:", template_dir)
        return None

    if output_dir.exists():
        answer = input("すでに存在します。上書きしますか？(y/n)：").lower()
        if answer != "y":
            return None
        shutil.rmtree(output_dir)

    shutil.copytree(template_dir, output_dir)

    replacements = {
        "{{PROJECT}}": project,
        "{{DATE}}": today,
        "{{TEL}}": tel,
        "{{TEL_DISPLAY}}": tel_display,
    }

    for html_path in output_dir.rglob("*.html"):
        replace_in_file(html_path, replacements)
        inject_body_classes(html_path, template)
        normalize_html(html_path)

    copy_exiga_dist_to_output(output_dir)
    print("作成完了：", output_dir)
    return output_dir


# -----------------------------
# エントリーポイント
# -----------------------------
def main() -> None:
    base_dir = Path(__file__).parent

    mode = input("モードを選択： 1=新規生成 / 2=CSS同期 > ").strip()

    # -------------------------
    # 2) CSS同期モード
    # -------------------------
    if mode == "2":
        target = ask_existing_output_dir(base_dir)
        if not target:
            return

        copy_exiga_dist_to_output(target)
        print("CSS同期完了：", target)
        return

    # -------------------------
    # 1) 新規生成モード
    # -------------------------
    project = input("案件名を入力してください：").strip()
    if not project:
        return

    template = ask_template()
    tel = input("電話番号（ハイフンなし）：").strip()
    tel_display = input("表示用電話番号：").strip()

    make_project(project, template, tel, tel_display)


if __name__ == "__main__":
    main()
