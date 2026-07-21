from __future__ import annotations

import re
from html import escape


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}

CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


def normalize_project_display_name(project_name: str) -> str:
    normalized = CONTROL_CHAR_PATTERN.sub(" ", project_name)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        raise ValueError("案件名は空欄または制御文字だけにできません。")

    return normalized


def sanitize_project_slug(project_name: str) -> str:
    display_name = normalize_project_display_name(project_name)

    normalized = re.sub(
        r'[<>:"/\\|?*\x00-\x1f\x7f]+',
        "-",
        display_name,
    )
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    normalized = normalized.strip(" .-_")

    if not normalized:
        raise ValueError(
            "案件名から有効なフォルダ名を作成できませんでした。"
        )

    reserved_base_name = normalized.split(".", 1)[0].upper()

    if reserved_base_name in WINDOWS_RESERVED_NAMES:
        normalized = f"project-{normalized}"

    return normalized


def escape_project_html(project_name: str) -> str:
    display_name = normalize_project_display_name(project_name)
    return escape(display_name, quote=True)


def sanitize_theme_name(project_name: str) -> str:
    display_name = normalize_project_display_name(project_name)

    return (
        display_name
        .replace("/*", "/ *")
        .replace("*/", "* /")
    )
