from __future__ import annotations

import argparse
import re
import shutil
import sys
import warnings
from datetime import date
from pathlib import Path
from uuid import uuid4

import filesystem_safety
from filesystem_safety import (
    DirectoryTransactionRecoveryError,
    assert_no_directory_transaction_artifacts,
    rename_with_retry,
)

from generation_manifest import (
    GenerationManifestError,
    MANIFEST_FILENAME,
    read_generation_manifest,
    write_generation_manifest,
)

from starter_contract import (
    StarterContractError,
    validate_starter_contract,
)

from project_naming import (
    escape_project_html,
    sanitize_project_slug,
)
from console_safety import configure_standard_streams


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
    return sanitize_project_slug(project_name)


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
        "{{PROJECT}}": escape_project_html(project_name),
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
    return validate_starter_contract(
        base_dir
    ).dist_root


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
    filesystem_safety.replace_directory_transactionally(
        staging_dir,
        destination_dir,
        rename_path=rename_with_retry,
    )


class DistRefreshRecoveryError(RuntimeError):
    def __init__(
        self,
        *,
        original_error: Exception,
        recovery_errors: list[
            tuple[str, Exception]
        ],
        backup_dist_dir: Path,
        backup_manifest_path: Path,
        failed_dist_dir: Path,
        failed_manifest_path: Path,
    ) -> None:
        self.original_error = original_error
        self.recovery_errors = tuple(
            recovery_errors
        )
        self.backup_dist_dir = (
            backup_dist_dir
        )
        self.backup_manifest_path = (
            backup_manifest_path
        )
        self.failed_dist_dir = (
            failed_dist_dir
        )
        self.failed_manifest_path = (
            failed_manifest_path
        )

        recovery_detail = "; ".join(
            (
                f"{label}: "
                f"{type(error).__name__}: "
                f"{error}"
            )
            for label, error
            in recovery_errors
        )

        super().__init__(
            "dist/manifest transactionに失敗し、"
            "rollbackも完了しませんでした。"
            f" original="
            f"{type(original_error).__name__}: "
            f"{original_error};"
            f" recovery={recovery_detail};"
            f" backup_dist={backup_dist_dir};"
            f" backup_manifest="
            f"{backup_manifest_path};"
            f" failed_dist={failed_dist_dir};"
            f" failed_manifest="
            f"{failed_manifest_path}"
        )


DIST_TRANSACTION_PREFIXES = (
    ".dist.tmp-",
    f".{MANIFEST_FILENAME}.tmp-",
    ".dist.backup-",
    f".{MANIFEST_FILENAME}.backup-",
    ".dist.failed-",
    f".{MANIFEST_FILENAME}.failed-",
)


def find_dist_transaction_artifacts(
    output_dir: Path,
) -> tuple[Path, ...]:
    if not output_dir.is_dir():
        return ()

    return tuple(
        sorted(
            (
                path
                for path
                in output_dir.iterdir()
                if any(
                    path.name.startswith(
                        prefix
                    )
                    for prefix
                    in DIST_TRANSACTION_PREFIXES
                )
            ),
            key=lambda path: path.name,
        )
    )


def assert_no_dist_transaction_artifacts(
    output_dir: Path,
) -> None:
    artifacts = (
        find_dist_transaction_artifacts(
            output_dir
        )
    )

    if not artifacts:
        return

    detail = "\n".join(
        f"- {path}"
        for path in artifacts
    )

    raise RuntimeError(
        "前回のdist transaction残骸が"
        "見つかりました。"
        "自動更新を停止します。"
        "内容を確認してから復旧または削除"
        "してください。\n"
        f"{detail}"
    )


def remove_path_quietly(
    path: Path,
) -> None:
    try:
        if not path.exists():
            return

        if path.is_dir():
            shutil.rmtree(path)
            return

        path.unlink()
    except OSError as error:
        warnings.warn(
            "transaction cleanupに"
            "失敗しました。"
            f" path={path}"
            f" error={type(error).__name__}: "
            f"{error}",
            RuntimeWarning,
            stacklevel=2,
        )


def replace_dist_and_manifest_transactionally(
    *,
    staging_dist_dir: Path,
    staging_manifest_path: Path,
    output_dir: Path,
) -> None:
    destination_dist_dir = (
        output_dir
        / "dist"
    )
    destination_manifest_path = (
        output_dir
        / MANIFEST_FILENAME
    )

    if (
        destination_dist_dir.exists()
        and not destination_dist_dir.is_dir()
    ):
        raise FileExistsError(
            "既存distがディレクトリでは"
            "ありません: "
            f"{destination_dist_dir}"
        )

    if (
        destination_manifest_path.exists()
        and not destination_manifest_path.is_file()
    ):
        raise FileExistsError(
            "既存manifestがファイルでは"
            "ありません: "
            f"{destination_manifest_path}"
        )

    transaction_id = uuid4().hex

    backup_dist_dir = output_dir / (
        f".dist.backup-{transaction_id}"
    )
    backup_manifest_path = output_dir / (
        f".{MANIFEST_FILENAME}.backup-"
        f"{transaction_id}"
    )
    failed_dist_dir = output_dir / (
        f".dist.failed-{transaction_id}"
    )
    failed_manifest_path = output_dir / (
        f".{MANIFEST_FILENAME}.failed-"
        f"{transaction_id}"
    )

    had_dist = (
        destination_dist_dir.exists()
    )
    had_manifest = (
        destination_manifest_path.exists()
    )

    backed_up_dist = False
    backed_up_manifest = False
    installed_dist = False
    installed_manifest = False

    try:
        if had_dist:
            rename_with_retry(
                destination_dist_dir,
                backup_dist_dir,
            )
            backed_up_dist = True

        if had_manifest:
            rename_with_retry(
                destination_manifest_path,
                backup_manifest_path,
            )
            backed_up_manifest = True

        rename_with_retry(
            staging_dist_dir,
            destination_dist_dir,
        )
        installed_dist = True

        rename_with_retry(
            staging_manifest_path,
            destination_manifest_path,
        )
        installed_manifest = True
    except Exception as original_error:
        recovery_errors: list[
            tuple[str, Exception]
        ] = []

        def attempt_recovery_rename(
            *,
            label: str,
            source: Path,
            destination: Path,
        ) -> bool:
            try:
                rename_with_retry(
                    source,
                    destination,
                )
            except Exception as error:
                recovery_errors.append(
                    (label, error)
                )
                return False

            return True

        if (
            installed_manifest
            and destination_manifest_path.exists()
        ):
            attempt_recovery_rename(
                label=(
                    "new manifest quarantine"
                ),
                source=(
                    destination_manifest_path
                ),
                destination=(
                    failed_manifest_path
                ),
            )

        if (
            installed_dist
            and destination_dist_dir.exists()
        ):
            attempt_recovery_rename(
                label="new dist quarantine",
                source=destination_dist_dir,
                destination=failed_dist_dir,
            )

        if (
            backed_up_dist
            and backup_dist_dir.exists()
        ):
            if destination_dist_dir.exists():
                recovery_errors.append(
                    (
                        "old dist restore",
                        RuntimeError(
                            "復元先distが"
                            "使用中です: "
                            f"{destination_dist_dir}"
                        ),
                    )
                )
            else:
                attempt_recovery_rename(
                    label="old dist restore",
                    source=backup_dist_dir,
                    destination=(
                        destination_dist_dir
                    ),
                )

        if (
            backed_up_manifest
            and backup_manifest_path.exists()
        ):
            if (
                destination_manifest_path.exists()
            ):
                recovery_errors.append(
                    (
                        "old manifest restore",
                        RuntimeError(
                            "復元先manifestが"
                            "使用中です: "
                            f"{destination_manifest_path}"
                        ),
                    )
                )
            else:
                attempt_recovery_rename(
                    label=(
                        "old manifest restore"
                    ),
                    source=(
                        backup_manifest_path
                    ),
                    destination=(
                        destination_manifest_path
                    ),
                )

        if recovery_errors:
            raise DistRefreshRecoveryError(
                original_error=original_error,
                recovery_errors=(
                    recovery_errors
                ),
                backup_dist_dir=(
                    backup_dist_dir
                ),
                backup_manifest_path=(
                    backup_manifest_path
                ),
                failed_dist_dir=(
                    failed_dist_dir
                ),
                failed_manifest_path=(
                    failed_manifest_path
                ),
            ) from original_error

        remove_path_quietly(
            failed_dist_dir
        )
        remove_path_quietly(
            failed_manifest_path
        )

        raise
    else:
        remove_path_quietly(
            backup_dist_dir
        )
        remove_path_quietly(
            backup_manifest_path
        )



def refresh_dist(
    *,
    base_dir: Path,
    project_name: str,
) -> Path:
    outputs_dir = base_dir / "outputs"
    output_dir = (
        outputs_dir
        / sanitize_project_name(project_name)
    )

    if (
        not output_dir.exists()
        or not output_dir.is_dir()
    ):
        raise FileNotFoundError(
            f"対象案件フォルダが見つかりません: {output_dir}"
        )

    assert_no_dist_transaction_artifacts(
        output_dir
    )

    existing_manifest_path = (
        output_dir
        / MANIFEST_FILENAME
    )
    existing_manifest = read_generation_manifest(
        existing_manifest_path
    )

    dist_root = resolve_exiga_dist(base_dir)
    staging_dist_dir = output_dir / (
        f".dist.tmp-{uuid4().hex}"
    )
    staging_manifest_path = output_dir / (
        f".{MANIFEST_FILENAME}.tmp-"
        f"{uuid4().hex}"
    )

    try:
        copy_exiga_dist(
            dist_root,
            staging_dist_dir,
        )

        write_generation_manifest(
            staging_manifest_path,
            base_dir=base_dir,
            starter_root=dist_root.parent,
            dist_root=staging_dist_dir,
            template_name=None,
            project_name=project_name,
            project_slug=output_dir.name,
            generated_date=None,
            operation="refresh-dist",
            required_assets=REQUIRED_DIST_FILES,
            existing_manifest=existing_manifest,
        )

        replace_dist_and_manifest_transactionally(
            staging_dist_dir=staging_dist_dir,
            staging_manifest_path=(
                staging_manifest_path
            ),
            output_dir=output_dir,
        )
    finally:
        remove_path_quietly(
            staging_dist_dir
        )
        remove_path_quietly(
            staging_manifest_path
        )

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

    outputs_dir = base_dir / "outputs"
    output_dir = outputs_dir / sanitize_project_name(project_name)
    assert_no_directory_transaction_artifacts(
        output_dir
    )

    if output_dir.exists() and not output_dir.is_dir():
        raise FileExistsError(
            f"同名の出力先がディレクトリではありません: {output_dir}"
        )

    if output_dir.exists() and not force and not confirm_overwrite(output_dir):
        raise SystemExit("生成を中止しました。")

    dist_root = resolve_exiga_dist(base_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = outputs_dir / f".{output_dir.name}.tmp-{uuid4().hex}"
    preserve_staging = False

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
        copy_exiga_dist(
            dist_root,
            staging_dir / "dist",
        )

        write_generation_manifest(
            staging_dir / MANIFEST_FILENAME,
            base_dir=base_dir,
            starter_root=dist_root.parent,
            dist_root=staging_dir / "dist",
            template_name=template_name,
            project_name=project_name,
            project_slug=output_dir.name,
            generated_date=generated_date,
            operation="create",
            required_assets=REQUIRED_DIST_FILES,
        )

        replace_directory_transactionally(
            staging_dir,
            output_dir,
        )
    except DirectoryTransactionRecoveryError:
        preserve_staging = True
        raise
    finally:
        if (
            staging_dir.exists()
            and not preserve_staging
        ):
            shutil.rmtree(staging_dir, ignore_errors=True)

    return output_dir


def main() -> None:
    configure_standard_streams()
    args = parse_args()
    base_dir = Path(__file__).resolve().parent

    if args.refresh_dist:
        if not args.project:
            print("`--refresh-dist` を使う場合は `--project` を指定してください。")
            raise SystemExit(1)

        try:
            output_dir = refresh_dist(base_dir=base_dir, project_name=args.project)
        except (OSError, ValueError, StarterContractError, GenerationManifestError) as error:
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
    except (OSError, ValueError, StarterContractError, GenerationManifestError) as error:
        print(error)
        raise SystemExit(1) from error

    print(f"\n生成完了: {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n処理を中断しました。")
        sys.exit(1)
