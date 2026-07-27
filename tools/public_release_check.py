from __future__ import annotations

import argparse
import ipaddress
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import (
    SplitResult,
    unquote,
    urljoin,
    urlsplit,
    urlunsplit,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(REPOSITORY_ROOT),
    )

from console_safety import configure_standard_streams


MAX_SCANNED_ENTRIES = 20_000
MAX_DIRECTORY_DEPTH = 64
MAX_TEXT_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_TEXT_BYTES = 100 * 1024 * 1024
HTML_VALIDATE_COMMAND_LENGTH = 24_000

HTML_SUFFIXES = frozenset(
    {
        ".html",
        ".htm",
    }
)
TEXT_SUFFIXES = frozenset(
    {
        ".css",
        ".csv",
        ".cjs",
        ".html",
        ".htm",
        ".js",
        ".json",
        ".jsx",
        ".map",
        ".md",
        ".mjs",
        ".php",
        ".svg",
        ".text",
        ".txt",
        ".tsv",
        ".webmanifest",
        ".xml",
        ".yaml",
        ".yml",
    }
)
TEXT_FILENAMES = frozenset(
    {
        ".htaccess",
    }
)
FORBIDDEN_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
    }
)
FORBIDDEN_EXACT_FILENAMES = frozenset(
    {
        ".project-generator-wordpress.json",
        "project-manifest.json",
    }
)
FORBIDDEN_SUFFIXES = (
    ".7z",
    ".bak",
    ".key",
    ".old",
    ".p12",
    ".pem",
    ".pfx",
    ".rar",
    ".tar",
    ".tar.gz",
    ".zip",
)
TRANSACTION_ARTIFACT_PATTERN = re.compile(
    r"^\..+\.(?:wp-)?(?:tmp|backup|failed)-.+$",
    re.IGNORECASE,
)
INTERNAL_TRANSACTION_PATTERN = re.compile(
    (
        r"^\.(?:dist|project-manifest\.json)\."
        r"(?:tmp|backup|failed)-.+$"
    ),
    re.IGNORECASE,
)

DUMMY_PATTERNS = (
    (
        "DUMMY_PLACEHOLDER",
        re.compile(r"\{\{[^{}\r\n]+\}\}"),
        "未置換の{{...}} placeholderがあります。",
    ),
    (
        "DUMMY_YEAR",
        re.compile(r"20XX", re.IGNORECASE),
        "ダミー年表記20XXがあります。",
    ),
    (
        "DUMMY_CIRCLE",
        re.compile(r"〇〇"),
        "ダミー表記〇〇があります。",
    ),
    (
        "DUMMY_EXAMPLE_DOMAIN",
        re.compile(
            r"(?<![a-z0-9-])example\.(?:com|net|org)(?![a-z0-9-])",
            re.IGNORECASE,
        ),
        "example.com / example.net / example.orgが残っています。",
    ),
    (
        "DUMMY_EXAMPLE_EMAIL",
        re.compile(
            r"info@example\.com",
            re.IGNORECASE,
        ),
        "ダミー連絡先info@example.comが残っています。",
    ),
    (
        "DUMMY_REPLACEMENT_NOTE",
        re.compile(r"差し替えメモ"),
        "差し替えメモが残っています。",
    ),
    (
        "DUMMY_GENERATOR_CREDIT",
        re.compile(
            r"Generated from project-generator",
            re.IGNORECASE,
        ),
        "Generator由来の公開前削除文言が残っています。",
    ),
)
DEVELOPMENT_URL_PATTERN = re.compile(
    (
        r"(?:"
        r"localhost"
        r"|127\.0\.0\.1"
        r"|0\.0\.0\.0"
        r"|\[::1\]"
        r"|file://"
        r")"
    ),
    re.IGNORECASE,
)
MALFORMED_PERCENT_ESCAPE_PATTERN = re.compile(
    r"%(?![0-9A-Fa-f]{2})"
)
URL_CONTROL_OR_SPACE_PATTERN = re.compile(
    r"[\x00-\x20\x7f]"
)
KNOWN_STARTER_COPY = (
    "トップページスターターです。案件開始時の土台として使える最小構成です。",
    "会社案内スターターです。案件に合わせて会社紹介を差し替えやすい構成にしています。",
    "サービス紹介スターターです。提供内容を整理して掲載しやすい最小構成にしています。",
    "お問い合わせスターターです。実務で差し替えやすい最小フォーム構成にしています。",
    "ランディングページスターターです。仕事用の最小構成として再利用しやすく整えています。",
    "店舗トップページスターターです。商品カテゴリ、店舗情報、来店導線を整理しやすい最小構成です。",
    "商品一覧スターターです。カテゴリ別の商品紹介と価格表示を整理しやすい最小構成です。",
    "店舗紹介スターターです。店の背景、こだわり、営業時間、アクセスを整理しやすい最小構成です。",
    "店舗向け問い合わせスターターです。商品相談や取り置き相談を受けやすい最小フォーム構成です。",
    "仕事用スターターとして最初の構成を整えた状態です。必要な情報へ差し替えて利用します。",
    "仕事用 LP の最小スターターとして使うための土台です。",
    "店舗・物販向けスターターとして商品と店舗情報を整理しやすい構成です。",
    "最小構成の問い合わせページスターターです。",
)


class PublicReleaseUsageError(RuntimeError):
    pass


@dataclass(frozen=True)
class Finding:
    relative_path: str
    line: int
    rule_id: str
    reason: str

    def sort_key(
        self,
    ) -> tuple[str, str, int, str, str]:
        return (
            self.relative_path.casefold(),
            self.relative_path,
            self.line,
            self.rule_id,
            self.reason,
        )

    def format(
        self,
    ) -> str:
        return (
            f"{self.relative_path}:{self.line}: "
            f"{self.rule_id}: {self.reason}"
        )


@dataclass(frozen=True)
class BaseUrl:
    netloc: str
    origin: tuple[str, str, int]
    path_prefix: str

    @property
    def root_url(
        self,
    ) -> str:
        return urlunsplit(
            (
                "https",
                self.netloc,
                self.path_prefix,
                "",
                "",
            )
        )

    def document_url(
        self,
        relative_path: str,
    ) -> str:
        return urljoin(
            self.root_url,
            relative_path.replace(
                os.sep,
                "/",
            ),
        )


@dataclass(frozen=True)
class ValidatedHttpsUrl:
    parsed: SplitResult
    origin: tuple[str, str, int]
    decoded_path: str


@dataclass(frozen=True)
class HtmlReference:
    attribute: str
    value: str
    line: int


@dataclass(frozen=True)
class FormAction:
    value: str | None
    line: int
    present: bool


@dataclass
class HtmlDocument:
    titles: list[tuple[int, str]]
    descriptions: list[tuple[int, str]]
    canonicals: list[tuple[int, str]]
    og_titles: list[tuple[int, str]]
    og_descriptions: list[tuple[int, str]]
    og_urls: list[tuple[int, str]]
    og_images: list[tuple[int, str]]
    references: list[HtmlReference]
    form_actions: list[FormAction]
    fragments: set[str]
    base_href: str | None


class PublicHtmlParser(HTMLParser):
    def __init__(
        self,
    ) -> None:
        super().__init__(
            convert_charrefs=True
        )
        self.titles: list[
            tuple[int, list[str]]
        ] = []
        self.descriptions: list[
            tuple[int, str]
        ] = []
        self.canonicals: list[
            tuple[int, str]
        ] = []
        self.og_titles: list[
            tuple[int, str]
        ] = []
        self.og_descriptions: list[
            tuple[int, str]
        ] = []
        self.og_urls: list[
            tuple[int, str]
        ] = []
        self.og_images: list[
            tuple[int, str]
        ] = []
        self.references: list[
            HtmlReference
        ] = []
        self.form_actions: list[
            FormAction
        ] = []
        self.fragments: set[str] = set()
        self.base_href: str | None = None
        self.active_title: list[str] | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        tag_name = tag.casefold()
        line = self.getpos()[0]
        normalized_attrs = [
            (
                name.casefold(),
                "" if value is None else value,
            )
            for name, value in attrs
        ]
        attr_map = dict(
            normalized_attrs
        )

        identifier = attr_map.get("id")
        if identifier:
            self.fragments.add(identifier)

        if (
            tag_name == "a"
            and attr_map.get("name")
        ):
            self.fragments.add(
                attr_map["name"]
            )

        if tag_name == "title":
            title_parts: list[str] = []
            self.titles.append(
                (
                    line,
                    title_parts,
                )
            )
            self.active_title = title_parts

        if tag_name == "meta":
            name = attr_map.get(
                "name",
                "",
            ).strip().casefold()
            property_name = attr_map.get(
                "property",
                "",
            ).strip().casefold()
            content = attr_map.get(
                "content",
                "",
            )

            if name == "description":
                self.descriptions.append(
                    (
                        line,
                        content,
                    )
                )

            og_targets = {
                "og:title": self.og_titles,
                "og:description": (
                    self.og_descriptions
                ),
                "og:url": self.og_urls,
                "og:image": self.og_images,
            }
            target = og_targets.get(
                property_name
            )
            if target is not None:
                target.append(
                    (
                        line,
                        content,
                    )
                )

        if tag_name == "link":
            rel_tokens = {
                token.casefold()
                for token in attr_map.get(
                    "rel",
                    "",
                ).split()
            }
            if "canonical" in rel_tokens:
                self.canonicals.append(
                    (
                        line,
                        attr_map.get(
                            "href",
                            "",
                        ),
                    )
                )

        if (
            tag_name == "base"
            and self.base_href is None
            and "href" in attr_map
        ):
            self.base_href = attr_map["href"]

        for attribute in (
            "href",
            "src",
            "poster",
        ):
            if attribute in attr_map:
                self.references.append(
                    HtmlReference(
                        attribute=attribute,
                        value=attr_map[attribute],
                        line=line,
                    )
                )

        if "srcset" in attr_map:
            for value in parse_srcset(
                attr_map["srcset"]
            ):
                self.references.append(
                    HtmlReference(
                        attribute="srcset",
                        value=value,
                        line=line,
                    )
                )

        if tag_name == "form":
            action_values = [
                value
                for name, value
                in normalized_attrs
                if name == "action"
            ]
            self.form_actions.append(
                FormAction(
                    value=(
                        action_values[-1]
                        if action_values
                        else None
                    ),
                    line=line,
                    present=bool(
                        action_values
                    ),
                )
            )

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[
            tuple[str, str | None]
        ],
    ) -> None:
        self.handle_starttag(
            tag,
            attrs,
        )
        self.handle_endtag(tag)

    def handle_endtag(
        self,
        tag: str,
    ) -> None:
        if tag.casefold() == "title":
            self.active_title = None

    def handle_data(
        self,
        data: str,
    ) -> None:
        if self.active_title is not None:
            self.active_title.append(data)

    def document(
        self,
    ) -> HtmlDocument:
        return HtmlDocument(
            titles=[
                (
                    line,
                    "".join(parts),
                )
                for line, parts in self.titles
            ],
            descriptions=self.descriptions,
            canonicals=self.canonicals,
            og_titles=self.og_titles,
            og_descriptions=(
                self.og_descriptions
            ),
            og_urls=self.og_urls,
            og_images=self.og_images,
            references=self.references,
            form_actions=self.form_actions,
            fragments=self.fragments,
            base_href=self.base_href,
        )


def parse_srcset(
    value: str,
) -> tuple[str, ...]:
    candidates: list[str] = []
    index = 0
    length = len(value)

    while index < length:
        while (
            index < length
            and (
                value[index].isspace()
                or value[index] == ","
            )
        ):
            index += 1

        if index >= length:
            break

        start = index
        is_data_url = value[
            index:
        ].casefold().startswith(
            "data:"
        )

        while (
            index < length
            and not value[index].isspace()
            and (
                is_data_url
                or value[index] != ","
            )
        ):
            index += 1

        candidate = value[
            start:index
        ].rstrip(",")
        if candidate:
            candidates.append(candidate)

        while (
            index < length
            and value[index] != ","
        ):
            index += 1

        if index < length:
            index += 1

    return tuple(candidates)


def normalized_origin(
    parsed_url,
) -> tuple[str, str, int] | None:
    scheme = parsed_url.scheme.casefold()
    hostname = parsed_url.hostname

    if not scheme or not hostname:
        return None

    try:
        port = parsed_url.port
    except ValueError:
        return None

    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
        else:
            return None

    return (
        scheme,
        hostname.casefold(),
        port,
    )


def decode_url_path(
    path: str,
) -> str:
    try:
        return unquote(
            path,
            encoding="utf-8",
            errors="strict",
        )
    except UnicodeDecodeError as error:
        raise ValueError(
            "URL pathのpercent encodingが"
            "UTF-8ではありません。"
        ) from error


def has_url_whitespace_or_control(
    value: str,
) -> bool:
    return bool(
        URL_CONTROL_OR_SPACE_PATTERN.search(
            value
        )
        or any(
            character.isspace()
            or unicodedata.category(
                character
            ).startswith("C")
            for character in value
        )
    )


def validate_https_absolute_url(
    value: str,
    *,
    forbid_query_and_fragment: bool,
) -> tuple[
    ValidatedHttpsUrl | None,
    str | None,
]:
    if not value:
        return (
            None,
            "HTTPS絶対URLが空です。",
        )

    if has_url_whitespace_or_control(
        value
    ):
        return (
            None,
            "URLに空白またはcontrol文字を"
            "含めることはできません。",
        )

    if (
        MALFORMED_PERCENT_ESCAPE_PATTERN
        .search(value)
    ):
        return (
            None,
            "URLに壊れたpercent escapeが"
            "あります。",
        )

    try:
        parsed = urlsplit(value)
    except ValueError as error:
        return (
            None,
            f"URLを解析できません: {error}",
        )

    if (
        parsed.scheme.casefold() != "https"
        or not parsed.netloc
        or not parsed.hostname
    ):
        return (
            None,
            "HTTPS絶対URLである必要が"
            "あります。",
        )

    if (
        parsed.username is not None
        or parsed.password is not None
    ):
        return (
            None,
            "userinfoを含めることは"
            "できません。",
        )

    if (
        forbid_query_and_fragment
        and (
            "?" in value
            or "#" in value
        )
    ):
        return (
            None,
            "queryとfragmentは空delimiter"
            "を含めて指定できません。",
        )

    authority = parsed.netloc.rsplit(
        "@",
        1,
    )[-1]
    if "%" in authority:
        return (
            None,
            "hostnameにpercent escapeは"
            "指定できません。",
        )

    if authority.endswith(":"):
        return (
            None,
            "空portは指定できません。",
        )

    hostname = parsed.hostname
    if (
        hostname is None
        or has_url_whitespace_or_control(
            hostname
        )
    ):
        return (
            None,
            "hostnameに空白またはcontrol文字"
            "を含めることはできません。",
        )

    is_bracketed_ipv6 = (
        authority.startswith("[")
    )
    if is_bracketed_ipv6:
        closing_bracket = authority.find(
            "]"
        )
        suffix = authority[
            closing_bracket + 1:
        ]
        if (
            closing_bracket < 0
            or (
                suffix
                and not suffix.startswith(":")
            )
        ):
            return (
                None,
                "IPv6 authorityが不正です。",
            )

        try:
            ipaddress.IPv6Address(
                hostname
            )
        except ValueError as error:
            return (
                None,
                f"IPv6 hostnameが不正です: {error}",
            )
    else:
        try:
            hostname.encode("idna")
        except UnicodeError as error:
            return (
                None,
                f"hostnameが不正です: {error}",
            )

    try:
        parsed.port
    except ValueError as error:
        return (
            None,
            f"portが不正です: {error}",
        )

    origin = normalized_origin(parsed)
    if origin is None:
        return (
            None,
            "URLのoriginまたはportが"
            "不正です。",
        )

    try:
        decoded_path = decode_url_path(
            parsed.path or "/"
        )
    except ValueError as error:
        return (
            None,
            str(error),
        )

    return (
        ValidatedHttpsUrl(
            parsed=parsed,
            origin=origin,
            decoded_path=decoded_path,
        ),
        None,
    )


def has_parent_segment(
    decoded_path: str,
) -> bool:
    return ".." in decoded_path.replace(
        "\\",
        "/",
    ).split("/")


def normalize_base_url(
    value: str,
) -> BaseUrl:
    validated, error = (
        validate_https_absolute_url(
            value,
            forbid_query_and_fragment=True,
        )
    )
    if (
        validated is None
        or error is not None
    ):
        raise PublicReleaseUsageError(
            "--base-urlが不正です: "
            f"{error or '詳細なし'}"
        )

    if (
        "\\" in validated.decoded_path
        or has_parent_segment(
            validated.decoded_path
        )
    ):
        raise PublicReleaseUsageError(
            "--base-urlのpathにbackslashや"
            "親directory参照は指定できません。"
        )

    normalized_path = posixpath.normpath(
        validated.decoded_path
    )
    if not normalized_path.startswith("/"):
        normalized_path = (
            f"/{normalized_path}"
        )

    path_prefix = (
        "/"
        if normalized_path == "/"
        else (
            normalized_path.rstrip("/")
            + "/"
        )
    )

    return BaseUrl(
        netloc=validated.parsed.netloc,
        origin=validated.origin,
        path_prefix=path_prefix,
    )


def resolve_root(
    value: str,
) -> Path:
    candidate = Path(value).expanduser()

    try:
        resolved = candidate.resolve(
            strict=True
        )
    except OSError as error:
        raise PublicReleaseUsageError(
            "--rootを解決できません: "
            f"{candidate}: "
            f"{type(error).__name__}: {error}"
        ) from error

    if not resolved.is_dir():
        raise PublicReleaseUsageError(
            "--rootは存在するdirectoryを"
            f"指定してください: {resolved}"
        )

    return resolved


def relative_name(
    root: Path,
    path: Path,
) -> str:
    return path.relative_to(
        root
    ).as_posix()


def is_forbidden_file(
    name: str,
) -> bool:
    folded = name.casefold()

    if (
        folded == ".env"
        or folded.startswith(".env.")
        or folded
        in FORBIDDEN_EXACT_FILENAMES
    ):
        return True

    if (
        folded.startswith("id_rsa")
        or folded.startswith(
            "id_ed25519"
        )
        or folded.endswith("~")
    ):
        return True

    return any(
        folded.endswith(suffix)
        for suffix in FORBIDDEN_SUFFIXES
    )


def is_transaction_artifact(
    name: str,
) -> bool:
    return bool(
        TRANSACTION_ARTIFACT_PATTERN.match(
            name
        )
        or INTERNAL_TRANSACTION_PATTERN.match(
            name
        )
    )


def dir_entry_is_junction(
    entry,
) -> bool:
    entry_checker = getattr(
        entry,
        "is_junction",
        None,
    )
    if callable(entry_checker):
        return bool(entry_checker())

    path_checker = getattr(
        Path(entry.path),
        "is_junction",
        None,
    )
    if callable(path_checker):
        return bool(path_checker())

    return False


def discover_files(
    root: Path,
) -> tuple[list[Path], list[Finding]]:
    files: list[Path] = []
    findings: list[Finding] = []
    pending: list[
        tuple[Path, int]
    ] = [
        (
            root,
            0,
        )
    ]
    entry_count = 0

    while pending:
        directory, depth = pending.pop()

        try:
            with os.scandir(
                directory
            ) as iterator:
                entries = sorted(
                    iterator,
                    key=lambda entry: (
                        entry.name.casefold(),
                        entry.name,
                    ),
                )
        except OSError as error:
            display_path = (
                "."
                if directory == root
                else relative_name(
                    root,
                    directory,
                )
            )
            findings.append(
                Finding(
                    relative_path=(
                        display_path
                    ),
                    line=1,
                    rule_id=(
                        "PATH_SCAN_ERROR"
                    ),
                    reason=(
                        "directoryを読み取れません: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                )
            )
            continue

        child_directories: list[
            tuple[Path, int]
        ] = []

        for entry in entries:
            entry_count += 1
            if (
                entry_count
                > MAX_SCANNED_ENTRIES
            ):
                raise (
                    PublicReleaseUsageError(
                        "公開対象のentry数が上限"
                        f"{MAX_SCANNED_ENTRIES}件を"
                        "超えました。公開rootを"
                        "絞り込んでください。"
                    )
                )

            path = Path(entry.path)
            rel = relative_name(
                root,
                path,
            )

            try:
                if dir_entry_is_junction(
                    entry
                ):
                    findings.append(
                        Finding(
                            relative_path=rel,
                            line=1,
                            rule_id=(
                                "JUNCTION_UNCHECKED"
                            ),
                            reason=(
                                "junctionは公開範囲を"
                                "安全に検査できません。"
                            ),
                        )
                    )
                    continue

                if entry.is_symlink():
                    findings.append(
                        Finding(
                            relative_path=rel,
                            line=1,
                            rule_id=(
                                "SYMLINK_UNCHECKED"
                            ),
                            reason=(
                                "symlinkは公開範囲を"
                                "安全に検査できません。"
                            ),
                        )
                    )
                    continue

                if entry.is_dir(
                    follow_symlinks=False
                ):
                    if is_transaction_artifact(
                        entry.name
                    ):
                        findings.append(
                            Finding(
                                relative_path=rel,
                                line=1,
                                rule_id=(
                                    "FORBIDDEN_TRANSACTION_ARTIFACT"
                                ),
                                reason=(
                                    "未解決のtransaction"
                                    "残骸directoryです。"
                                ),
                            )
                        )
                        continue

                    if (
                        entry.name.casefold()
                        in (
                            FORBIDDEN_DIRECTORY_NAMES
                        )
                    ):
                        findings.append(
                            Finding(
                                relative_path=rel,
                                line=1,
                                rule_id=(
                                    "FORBIDDEN_DIRECTORY"
                                ),
                                reason=(
                                    "公開禁止directory"
                                    f"です: {entry.name}"
                                ),
                            )
                        )
                        continue

                    next_depth = depth + 1
                    if (
                        next_depth
                        > MAX_DIRECTORY_DEPTH
                    ):
                        raise (
                            PublicReleaseUsageError(
                                "公開対象のdirectory"
                                "深度が上限"
                                f"{MAX_DIRECTORY_DEPTH}を"
                                "超えました。"
                            )
                        )

                    child_directories.append(
                        (
                            path,
                            next_depth,
                        )
                    )
                    continue

                if entry.is_file(
                    follow_symlinks=False
                ):
                    files.append(path)

                    if is_transaction_artifact(
                        entry.name
                    ):
                        findings.append(
                            Finding(
                                relative_path=rel,
                                line=1,
                                rule_id=(
                                    "FORBIDDEN_TRANSACTION_ARTIFACT"
                                ),
                                reason=(
                                    "未解決のtransaction"
                                    "残骸です。"
                                ),
                            )
                        )
                    elif is_forbidden_file(
                        entry.name
                    ):
                        findings.append(
                            Finding(
                                relative_path=rel,
                                line=1,
                                rule_id=(
                                    "FORBIDDEN_FILE"
                                ),
                                reason=(
                                    "公開禁止fileです: "
                                    f"{entry.name}"
                                ),
                            )
                        )
                    continue

                findings.append(
                    Finding(
                        relative_path=rel,
                        line=1,
                        rule_id=(
                            "UNSUPPORTED_FILE_TYPE"
                        ),
                        reason=(
                            "通常fileまたはdirectory"
                            "ではないため検査できません。"
                        ),
                    )
                )
            except OSError as error:
                findings.append(
                    Finding(
                        relative_path=rel,
                        line=1,
                        rule_id=(
                            "PATH_SCAN_ERROR"
                        ),
                        reason=(
                            "file種別を確認できません: "
                            f"{type(error).__name__}: "
                            f"{error}"
                        ),
                    )
                )

        pending.extend(
            reversed(
                child_directories
            )
        )

    files.sort(
        key=lambda path: (
            relative_name(
                root,
                path,
            ).casefold(),
            relative_name(
                root,
                path,
            ),
        )
    )
    return files, findings


def is_text_file(
    path: Path,
) -> bool:
    return (
        path.name.casefold()
        in TEXT_FILENAMES
        or path.suffix.casefold()
        in TEXT_SUFFIXES
    )


def read_public_text_files(
    root: Path,
    files: Iterable[Path],
) -> tuple[
    dict[Path, str],
    list[Finding],
]:
    texts: dict[Path, str] = {}
    findings: list[Finding] = []
    total_bytes = 0

    for path in files:
        if not is_text_file(path):
            continue

        rel = relative_name(
            root,
            path,
        )

        try:
            size = path.stat().st_size
        except OSError as error:
            findings.append(
                Finding(
                    relative_path=rel,
                    line=1,
                    rule_id=(
                        "TEXT_READ_ERROR"
                    ),
                    reason=(
                        "file sizeを取得できません: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                )
            )
            continue

        if size > MAX_TEXT_FILE_BYTES:
            raise PublicReleaseUsageError(
                f"text fileが{MAX_TEXT_FILE_BYTES}"
                "bytesの上限を超えています: "
                f"{rel}"
            )

        total_bytes += size
        if total_bytes > MAX_TOTAL_TEXT_BYTES:
            raise PublicReleaseUsageError(
                "検査対象textの合計sizeが"
                f"{MAX_TOTAL_TEXT_BYTES}bytesの"
                "上限を超えています。"
            )

        try:
            data = path.read_bytes()
        except OSError as error:
            findings.append(
                Finding(
                    relative_path=rel,
                    line=1,
                    rule_id=(
                        "TEXT_READ_ERROR"
                    ),
                    reason=(
                        "text fileを読み取れません: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                )
            )
            continue

        try:
            texts[path] = data.decode(
                "utf-8",
                errors="strict",
            )
        except UnicodeDecodeError as error:
            findings.append(
                Finding(
                    relative_path=rel,
                    line=1,
                    rule_id=(
                        "TEXT_INVALID_UTF8"
                    ),
                    reason=(
                        "UTF-8として読み取れません: "
                        f"{error}"
                    ),
                )
            )

    return texts, findings


def inspect_dummy_and_development_text(
    root: Path,
    texts: dict[Path, str],
) -> list[Finding]:
    findings: list[Finding] = []

    for path, text in texts.items():
        rel = relative_name(
            root,
            path,
        )
        for line_number, line in enumerate(
            text.splitlines(),
            start=1,
        ):
            for (
                rule_id,
                pattern,
                reason,
            ) in DUMMY_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        Finding(
                            relative_path=rel,
                            line=line_number,
                            rule_id=rule_id,
                            reason=reason,
                        )
                    )

            if any(
                phrase in line
                for phrase in (
                    KNOWN_STARTER_COPY
                )
            ):
                findings.append(
                    Finding(
                        relative_path=rel,
                        line=line_number,
                        rule_id=(
                            "DUMMY_STARTER_COPY"
                        ),
                        reason=(
                            "現行template由来の既知の"
                            "starter説明文が残っています。"
                        ),
                    )
                )

            if DEVELOPMENT_URL_PATTERN.search(
                line
            ):
                findings.append(
                    Finding(
                        relative_path=rel,
                        line=line_number,
                        rule_id=(
                            "DEVELOPMENT_URL"
                        ),
                        reason=(
                            "localhost等の開発用URL"
                            "が残っています。"
                        ),
                    )
                )

    return findings


def parse_html_document(
    text: str,
) -> HtmlDocument:
    parser = PublicHtmlParser()
    parser.feed(text)
    parser.close()
    return parser.document()


def add_single_value_findings(
    findings: list[Finding],
    *,
    relative_path: str,
    values: Sequence[
        tuple[int, str]
    ],
    label: str,
    count_rule: str,
    empty_rule: str,
) -> str | None:
    if len(values) != 1:
        line = (
            values[1][0]
            if len(values) > 1
            else 1
        )
        findings.append(
            Finding(
                relative_path=relative_path,
                line=line,
                rule_id=count_rule,
                reason=(
                    f"空でない{label}は"
                    "ちょうど1つ必要です。"
                    f"現在は{len(values)}件です。"
                ),
            )
        )
        return None

    line, value = values[0]
    stripped = value.strip()
    if not stripped:
        findings.append(
            Finding(
                relative_path=relative_path,
                line=line,
                rule_id=empty_rule,
                reason=(
                    f"{label}が空です。"
                ),
            )
        )
        return None

    return stripped


def is_path_within_base(
    decoded_path: str,
    base_url: BaseUrl,
) -> bool:
    prefix = base_url.path_prefix
    base_without_slash = (
        prefix.rstrip("/")
        if prefix != "/"
        else "/"
    )
    return (
        decoded_path == base_without_slash
        or decoded_path.startswith(prefix)
    )


def public_https_url_error(
    value: str,
    *,
    base_url: BaseUrl,
    require_site_location: bool,
    forbid_query_and_fragment: bool,
) -> str | None:
    validated, error = (
        validate_https_absolute_url(
            value,
            forbid_query_and_fragment=(
                forbid_query_and_fragment
            ),
        )
    )
    if (
        validated is None
        or error is not None
    ):
        return error or "URLが不正です。"

    if (
        "\\" in validated.decoded_path
        or has_parent_segment(
            validated.decoded_path
        )
    ):
        return (
            "URL pathにbackslashや親directory"
            "参照は指定できません。"
        )

    if require_site_location:
        if (
            validated.origin
            != base_url.origin
        ):
            return (
                "--base-urlとoriginが一致しません。"
            )
        if not is_path_within_base(
            validated.decoded_path,
            base_url,
        ):
            return (
                "--base-urlのpath配下では"
                "ありません。"
            )

    return None


def inspect_seo(
    relative_path: str,
    document: HtmlDocument,
    base_url: BaseUrl,
) -> list[Finding]:
    findings: list[Finding] = []

    add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.titles,
        label="title",
        count_rule="SEO_TITLE_COUNT",
        empty_rule="SEO_TITLE_EMPTY",
    )
    add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.descriptions,
        label="meta description",
        count_rule=(
            "SEO_DESCRIPTION_COUNT"
        ),
        empty_rule=(
            "SEO_DESCRIPTION_EMPTY"
        ),
    )
    canonical = add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.canonicals,
        label="canonical",
        count_rule=(
            "SEO_CANONICAL_COUNT"
        ),
        empty_rule=(
            "SEO_CANONICAL_EMPTY"
        ),
    )
    add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.og_titles,
        label="og:title",
        count_rule=(
            "SEO_OG_TITLE_COUNT"
        ),
        empty_rule=(
            "SEO_OG_TITLE_EMPTY"
        ),
    )
    add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.og_descriptions,
        label="og:description",
        count_rule=(
            "SEO_OG_DESCRIPTION_COUNT"
        ),
        empty_rule=(
            "SEO_OG_DESCRIPTION_EMPTY"
        ),
    )
    og_url = add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.og_urls,
        label="og:url",
        count_rule=(
            "SEO_OG_URL_COUNT"
        ),
        empty_rule=(
            "SEO_OG_URL_EMPTY"
        ),
    )
    og_image = add_single_value_findings(
        findings,
        relative_path=relative_path,
        values=document.og_images,
        label="og:image",
        count_rule=(
            "SEO_OG_IMAGE_COUNT"
        ),
        empty_rule=(
            "SEO_OG_IMAGE_EMPTY"
        ),
    )

    if canonical is not None:
        error = public_https_url_error(
            canonical,
            base_url=base_url,
            require_site_location=True,
            forbid_query_and_fragment=True,
        )
        if error is not None:
            findings.append(
                Finding(
                    relative_path=(
                        relative_path
                    ),
                    line=(
                        document.canonicals[
                            0
                        ][0]
                    ),
                    rule_id=(
                        "SEO_CANONICAL_URL"
                    ),
                    reason=error,
                )
            )

    if og_url is not None:
        error = public_https_url_error(
            og_url,
            base_url=base_url,
            require_site_location=True,
            forbid_query_and_fragment=False,
        )
        if error is not None:
            findings.append(
                Finding(
                    relative_path=(
                        relative_path
                    ),
                    line=(
                        document.og_urls[
                            0
                        ][0]
                    ),
                    rule_id="SEO_OG_URL",
                    reason=error,
                )
            )

    if og_image is not None:
        error = public_https_url_error(
            og_image,
            base_url=base_url,
            require_site_location=False,
            forbid_query_and_fragment=False,
        )
        if error is not None:
            findings.append(
                Finding(
                    relative_path=(
                        relative_path
                    ),
                    line=(
                        document.og_images[
                            0
                        ][0]
                    ),
                    rule_id=(
                        "SEO_OG_IMAGE_URL"
                    ),
                    reason=error,
                )
            )

    return findings


def url_path_to_local_path(
    *,
    root: Path,
    base_url: BaseUrl,
    decoded_path: str,
) -> Path | None:
    if not is_path_within_base(
        decoded_path,
        base_url,
    ):
        return None

    base_without_slash = (
        base_url.path_prefix.rstrip("/")
        if base_url.path_prefix != "/"
        else ""
    )

    if decoded_path == base_without_slash:
        relative_url_path = ""
    else:
        relative_url_path = decoded_path[
            len(
                base_url.path_prefix
            ):
        ]

    parts = [
        part
        for part in relative_url_path.split(
            "/"
        )
        if part
    ]
    candidate = root.joinpath(
        *parts
    )

    try:
        resolved_candidate = candidate.resolve(
            strict=False
        )
        resolved_candidate.relative_to(root)
    except (
        OSError,
        ValueError,
    ):
        return None

    if (
        decoded_path.endswith("/")
        or not relative_url_path
    ):
        return (
            resolved_candidate
            / "index.html"
        )

    try:
        if resolved_candidate.is_dir():
            return (
                resolved_candidate
                / "index.html"
            )
    except OSError:
        return resolved_candidate

    return resolved_candidate


def inspect_internal_reference(
    *,
    root: Path,
    base_url: BaseUrl,
    relative_path: str,
    document_url: str,
    document: HtmlDocument,
    reference: HtmlReference,
) -> list[Finding]:
    findings: list[Finding] = []
    value = reference.value.strip()

    try:
        raw_parsed = urlsplit(value)
    except ValueError as error:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_INVALID"
                ),
                reason=(
                    f"{reference.attribute} URLを"
                    f"解析できません: {error}"
                ),
            )
        ]

    scheme = raw_parsed.scheme.casefold()
    if scheme == "javascript":
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id="JAVASCRIPT_URL",
                reason=(
                    f"{reference.attribute}に"
                    "javascript: URLは"
                    "指定できません。"
                ),
            )
        ]

    if scheme in {
        "blob",
        "data",
        "mailto",
        "tel",
    }:
        return []

    if (
        scheme
        and scheme not in {
            "http",
            "https",
        }
    ):
        return []

    if "\\" in value:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_INVALID"
                ),
                reason=(
                    f"{reference.attribute} URLに"
                    "backslashは指定できません。"
                ),
            )
        ]

    resolution_base = document_url
    if document.base_href:
        resolution_base = urljoin(
            document_url,
            document.base_href,
        )

    try:
        resolved = urlsplit(
            urljoin(
                resolution_base,
                value,
            )
        )
    except ValueError as error:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_INVALID"
                ),
                reason=(
                    f"{reference.attribute} URLを"
                    f"解決できません: {error}"
                ),
            )
        ]

    resolved_origin = normalized_origin(
        resolved
    )
    if (
        resolved.scheme.casefold()
        in {
            "http",
            "https",
        }
        and resolved_origin is None
    ):
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_INVALID"
                ),
                reason=(
                    f"{reference.attribute} URLの"
                    "originまたはportが不正です。"
                ),
            )
        ]

    if resolved_origin != base_url.origin:
        return []

    try:
        decoded_path = decode_url_path(
            resolved.path or "/"
        )
    except ValueError as error:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_INVALID"
                ),
                reason=str(error),
            )
        ]

    if "\\" in decoded_path:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_OUTSIDE_ROOT"
                ),
                reason=(
                    f"{reference.attribute}がURL decode"
                    "後に公開root外を参照します。"
                ),
            )
        ]

    had_trailing_slash = (
        decoded_path.endswith("/")
    )
    decoded_path = posixpath.normpath(
        decoded_path
    )
    if not decoded_path.startswith("/"):
        decoded_path = f"/{decoded_path}"
    if (
        had_trailing_slash
        and decoded_path != "/"
    ):
        decoded_path = (
            decoded_path.rstrip("/")
            + "/"
        )

    if not is_path_within_base(
        decoded_path,
        base_url,
    ):
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_OUTSIDE_ROOT"
                ),
                reason=(
                    f"{reference.attribute}が"
                    "--base-urlのpath外を"
                    "参照します。"
                ),
            )
        ]

    local_path = url_path_to_local_path(
        root=root,
        base_url=base_url,
        decoded_path=decoded_path,
    )
    if local_path is None:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_OUTSIDE_ROOT"
                ),
                reason=(
                    f"{reference.attribute}を公開root"
                    "内へ安全に解決できません。"
                ),
            )
        ]

    try:
        exists = local_path.is_file()
    except OSError as error:
        return [
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_READ_ERROR"
                ),
                reason=(
                    "参照先を確認できません: "
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )
        ]

    if not exists:
        findings.append(
            Finding(
                relative_path=relative_path,
                line=reference.line,
                rule_id=(
                    "INTERNAL_REFERENCE_MISSING"
                ),
                reason=(
                    f"{reference.attribute}の参照先が"
                    "存在しません: "
                    f"{reference.value}"
                ),
            )
        )
        return findings

    if resolved.fragment:
        try:
            current_html = (
                local_path.resolve()
                == (
                    root
                    / relative_path
                ).resolve()
            )
        except OSError:
            current_html = False

        if current_html:
            fragment = unquote(
                resolved.fragment,
                encoding="utf-8",
                errors="replace",
            )
            if (
                fragment
                and fragment
                not in document.fragments
            ):
                findings.append(
                    Finding(
                        relative_path=(
                            relative_path
                        ),
                        line=reference.line,
                        rule_id=(
                            "FRAGMENT_MISSING"
                        ),
                        reason=(
                            "同一page内fragmentが"
                            "存在しません: "
                            f"#{fragment}"
                        ),
                    )
                )

    return findings


def inspect_form_actions(
    *,
    root: Path,
    base_url: BaseUrl,
    relative_path: str,
    document_url: str,
    document: HtmlDocument,
) -> list[Finding]:
    findings: list[Finding] = []

    for action in document.form_actions:
        if not action.present:
            findings.append(
                Finding(
                    relative_path=(
                        relative_path
                    ),
                    line=action.line,
                    rule_id=(
                        "FORM_ACTION_MISSING"
                    ),
                    reason=(
                        "formにaction属性が"
                        "ありません。"
                    ),
                )
            )
            continue

        value = (
            ""
            if action.value is None
            else action.value.strip()
        )
        folded = value.casefold()
        if (
            not value
            or value == "#"
            or value.startswith("#")
            or folded.startswith(
                "javascript:"
            )
        ):
            findings.append(
                Finding(
                    relative_path=(
                        relative_path
                    ),
                    line=action.line,
                    rule_id=(
                        "FORM_ACTION_INVALID"
                    ),
                    reason=(
                        "form actionが空、fragment、"
                        "#、またはjavascript:です。"
                    ),
                )
            )
            continue

        try:
            parsed = urlsplit(value)
        except ValueError as error:
            findings.append(
                Finding(
                    relative_path=(
                        relative_path
                    ),
                    line=action.line,
                    rule_id=(
                        "FORM_ACTION_INVALID"
                    ),
                    reason=(
                        "form actionを解析"
                        f"できません: {error}"
                    ),
                )
            )
            continue

        if (
            parsed.netloc
            or parsed.scheme
        ):
            if (
                parsed.scheme.casefold()
                != "https"
                or normalized_origin(
                    parsed
                ) is None
                or parsed.username
                is not None
                or parsed.password
                is not None
            ):
                findings.append(
                    Finding(
                        relative_path=(
                            relative_path
                        ),
                        line=action.line,
                        rule_id=(
                            "FORM_ACTION_INVALID"
                        ),
                        reason=(
                            "外部form actionは"
                            "userinfoを含まない"
                            "HTTPS絶対URLが必要です。"
                        ),
                    )
                )
                continue

            if (
                normalized_origin(
                    parsed
                )
                != base_url.origin
            ):
                continue

        findings.extend(
            inspect_internal_reference(
                root=root,
                base_url=base_url,
                relative_path=(
                    relative_path
                ),
                document_url=document_url,
                document=document,
                reference=HtmlReference(
                    attribute="action",
                    value=value,
                    line=action.line,
                ),
            )
        )

    return findings


def inspect_html_documents(
    *,
    root: Path,
    base_url: BaseUrl,
    texts: dict[Path, str],
) -> tuple[
    dict[Path, HtmlDocument],
    list[Finding],
]:
    documents: dict[
        Path,
        HtmlDocument,
    ] = {}
    findings: list[Finding] = []

    html_items = sorted(
        (
            (
                path,
                text,
            )
            for path, text in texts.items()
            if (
                path.suffix.casefold()
                in HTML_SUFFIXES
            )
        ),
        key=lambda item: (
            relative_name(
                root,
                item[0],
            ).casefold(),
            relative_name(
                root,
                item[0],
            ),
        ),
    )

    for path, text in html_items:
        rel = relative_name(
            root,
            path,
        )

        try:
            document = parse_html_document(
                text
            )
        except Exception as error:
            findings.append(
                Finding(
                    relative_path=rel,
                    line=1,
                    rule_id=(
                        "HTML_PARSE_ERROR"
                    ),
                    reason=(
                        "HTMLを解析できません: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                )
            )
            continue

        documents[path] = document
        findings.extend(
            inspect_seo(
                rel,
                document,
                base_url,
            )
        )

        document_url = (
            base_url.document_url(rel)
        )
        for reference in (
            document.references
        ):
            findings.extend(
                inspect_internal_reference(
                    root=root,
                    base_url=base_url,
                    relative_path=rel,
                    document_url=(
                        document_url
                    ),
                    document=document,
                    reference=reference,
                )
            )

        findings.extend(
            inspect_form_actions(
                root=root,
                base_url=base_url,
                relative_path=rel,
                document_url=document_url,
                document=document,
            )
        )

    return documents, findings


HtmlValidator = Callable[
    [Path, Sequence[Path]],
    Sequence[Finding],
]


def html_validate_environment(
) -> tuple[str, Path, Path]:
    node = shutil.which("node")
    if node is None:
        raise PublicReleaseUsageError(
            "Node.jsが見つかりません。"
            "html-validateをskipせず停止します。"
        )

    executable = (
        REPOSITORY_ROOT
        / "node_modules"
        / "html-validate"
        / "bin"
        / "html-validate.mjs"
    )
    if not executable.is_file():
        raise PublicReleaseUsageError(
            "localのhtml-validateが"
            "見つかりません。npm ci後に"
            "再実行してください。"
        )

    config = (
        REPOSITORY_ROOT
        / ".htmlvalidate.json"
    )
    if not config.is_file():
        raise PublicReleaseUsageError(
            ".htmlvalidate.jsonが"
            "見つかりません。"
        )

    return node, executable, config


def html_validate_batches(
    paths: Sequence[Path],
) -> tuple[
    tuple[Path, ...],
    ...,
]:
    batches: list[
        tuple[Path, ...]
    ] = []
    current: list[Path] = []
    current_length = 0

    for path in paths:
        path_length = len(str(path)) + 3
        if (
            current
            and (
                current_length
                + path_length
                > (
                    HTML_VALIDATE_COMMAND_LENGTH
                )
            )
        ):
            batches.append(
                tuple(current)
            )
            current = []
            current_length = 0

        current.append(path)
        current_length += path_length

    if current:
        batches.append(
            tuple(current)
        )

    return tuple(batches)


def run_html_validate(
    root: Path,
    html_paths: Sequence[Path],
) -> Sequence[Finding]:
    (
        node,
        executable,
        config,
    ) = html_validate_environment()
    findings: list[Finding] = []

    for batch in html_validate_batches(
        html_paths
    ):
        command = [
            node,
            str(executable),
            "--config",
            str(
                config.relative_to(
                    REPOSITORY_ROOT
                )
            ),
            "--formatter",
            "json",
            *(
                str(path)
                for path in batch
            ),
        ]

        try:
            result = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                check=False,
            )
        except (
            OSError,
            UnicodeError,
        ) as error:
            raise PublicReleaseUsageError(
                "html-validateを実行"
                "できません: "
                f"{type(error).__name__}: "
                f"{error}"
            ) from error

        if result.returncode not in {
            0,
            1,
        }:
            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or "詳細なし"
            )
            raise PublicReleaseUsageError(
                "html-validateが実行環境"
                "エラーで終了しました"
                f"（code {result.returncode}）: "
                f"{detail}"
            )

        if (
            result.returncode == 1
            and not result.stdout.strip()
        ):
            detail = (
                result.stderr.strip()
                or "詳細なし"
            )
            raise PublicReleaseUsageError(
                "html-validateが検査結果を"
                "返さず終了しました: "
                f"{detail}"
            )

        try:
            reports = json.loads(
                result.stdout or "[]"
            )
        except json.JSONDecodeError as error:
            raise PublicReleaseUsageError(
                "html-validateのJSON出力を"
                f"解析できません: {error}"
            ) from error

        for report in reports:
            reported_path = Path(
                report.get(
                    "filePath",
                    "",
                )
            )
            try:
                rel = relative_name(
                    root,
                    reported_path.resolve(),
                )
            except (
                OSError,
                ValueError,
            ):
                rel = reported_path.name

            for message in report.get(
                "messages",
                [],
            ):
                html_rule = (
                    message.get("ruleId")
                    or "unknown"
                )
                findings.append(
                    Finding(
                        relative_path=rel,
                        line=max(
                            1,
                            int(
                                message.get(
                                    "line",
                                    1,
                                )
                                or 1
                            ),
                        ),
                        rule_id=(
                            "HTML_VALIDATE/"
                            f"{html_rule}"
                        ),
                        reason=str(
                            message.get(
                                "message",
                                (
                                    "html-validate"
                                    " violation"
                                ),
                            )
                        ),
                    )
                )

    return findings


def unique_sorted_findings(
    findings: Iterable[Finding],
) -> list[Finding]:
    return sorted(
        set(findings),
        key=lambda finding: (
            finding.sort_key()
        ),
    )


def inspect_public_root(
    *,
    root: Path,
    base_url: BaseUrl,
    html_validator: (
        HtmlValidator
        | None
    ) = None,
) -> tuple[int, list[Finding]]:
    active_html_validator = (
        run_html_validate
        if html_validator is None
        else html_validator
    )
    files, findings = discover_files(
        root
    )
    texts, text_findings = (
        read_public_text_files(
            root,
            files,
        )
    )
    findings.extend(text_findings)
    findings.extend(
        inspect_dummy_and_development_text(
            root,
            texts,
        )
    )

    html_paths = [
        path
        for path in files
        if (
            path.suffix.casefold()
            in HTML_SUFFIXES
        )
    ]
    html_count = len(html_paths)
    if html_count == 0:
        findings.append(
            Finding(
                relative_path=".",
                line=1,
                rule_id="NO_HTML_FILES",
                reason=(
                    "検査対象HTMLが0件です。"
                ),
            )
        )

    (
        documents,
        html_findings,
    ) = inspect_html_documents(
        root=root,
        base_url=base_url,
        texts=texts,
    )
    findings.extend(html_findings)

    readable_html_paths = [
        path
        for path in html_paths
        if path in documents
    ]
    findings.extend(
        active_html_validator(
            root,
            readable_html_paths,
        )
    )

    return (
        html_count,
        unique_sorted_findings(
            findings
        ),
    )


def create_argument_parser(
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "公開予定file群をread-onlyで"
            "検査します。"
        )
    )
    parser.add_argument(
        "--root",
        required=True,
        help=(
            "serverへ公開する予定の"
            "file群のroot"
        ),
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help=(
            "案件のHTTPS本番base URL"
        ),
    )
    return parser


def configure_cli_streams(
) -> None:
    configure_standard_streams()

    for stream in (
        sys.stdout,
        sys.stderr,
    ):
        reconfigure = getattr(
            stream,
            "reconfigure",
            None,
        )
        if not callable(reconfigure):
            continue

        try:
            reconfigure(
                encoding="utf-8",
                errors="backslashreplace",
            )
        except (
            AttributeError,
            OSError,
            TypeError,
            ValueError,
        ):
            continue


def main(
    argv: Sequence[str] | None = None,
    *,
    html_validator: (
        HtmlValidator
        | None
    ) = None,
) -> int:
    configure_cli_streams()
    parser = create_argument_parser()
    args = parser.parse_args(argv)

    try:
        root = resolve_root(args.root)
        base_url = normalize_base_url(
            args.base_url
        )
        (
            html_count,
            findings,
        ) = inspect_public_root(
            root=root,
            base_url=base_url,
            html_validator=html_validator,
        )
    except PublicReleaseUsageError as error:
        print(
            f"使用上のエラー: {error}",
            file=sys.stderr,
        )
        print(
            "公開前検査終了: 検査を完了"
            "できませんでした。",
            file=sys.stderr,
        )
        return 2

    if findings:
        for finding in findings:
            print(finding.format())
        print(
            f"検出件数: {len(findings)}件"
        )
        print(
            "公開前検査失敗: 公開を"
            "停止してください。"
        )
        return 1

    print(
        f"対象HTML: {html_count}件"
    )
    print(
        "公開前検査成功: 公開停止事項は"
        "検出されませんでした。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
