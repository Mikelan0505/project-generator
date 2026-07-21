from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from generation_manifest import sha256_file


COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class StarterContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class StarterContract:
    schema_version: int
    repository_name: str
    required_commit: str
    required_assets: tuple[str, ...]
    copied_dist_roots: tuple[str, ...]
    dist_tree_sha256: str
    required_asset_sha256: dict[str, str]
    runtime_tokens: tuple[str, ...]


@dataclass(frozen=True)
class ValidatedStarter:
    repository_root: Path
    dist_root: Path
    head: str
    contract: StarterContract


def contract_path_for(base_dir: Path) -> Path:
    return base_dir / "starter-contract.json"


def require_string_list(
    data: dict[str, Any],
    key: str,
) -> tuple[str, ...]:
    value = data.get(key)

    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(item, str)
            and item.strip()
            for item in value
        )
    ):
        raise StarterContractError(
            f"`{key}`は空でない文字列配列である必要があります。"
        )

    normalized = tuple(
        item.strip().replace("\\", "/")
        for item in value
    )

    if len(set(normalized)) != len(normalized):
        raise StarterContractError(
            f"`{key}`に重複があります。"
        )

    return normalized


def require_sha256(
    data: dict[str, Any],
    key: str,
) -> str:
    value = data.get(key)

    if (
        not isinstance(value, str)
        or not SHA256_PATTERN.fullmatch(value)
    ):
        raise StarterContractError(
            f"`{key}`は64文字の小文字SHA-256である必要があります。"
        )

    return value


def validate_dist_asset_path(
    relative_path: str,
) -> None:
    if (
        relative_path.startswith("/")
        or relative_path.endswith("/")
        or "//" in relative_path
    ):
        raise StarterContractError(
            "requiredAssetsのパス形式が不正です: "
            f"{relative_path}"
        )

    path = PurePosixPath(relative_path)
    parts = path.parts

    if (
        len(parts) < 2
        or parts[0] != "dist"
        or any(
            part in {"", ".", ".."}
            for part in parts
        )
    ):
        raise StarterContractError(
            "requiredAssetsはdist配下の通常ファイルだけを"
            f"指定できます: {relative_path}"
        )


def require_asset_hashes(
    data: dict[str, Any],
    required_assets: tuple[str, ...],
) -> dict[str, str]:
    value = data.get("requiredAssetSha256")

    if not isinstance(value, dict):
        raise StarterContractError(
            "`requiredAssetSha256`はobjectである必要があります。"
        )

    normalized: dict[str, str] = {}

    for raw_path, raw_hash in value.items():
        if (
            not isinstance(raw_path, str)
            or not raw_path.strip()
            or not isinstance(raw_hash, str)
        ):
            raise StarterContractError(
                "`requiredAssetSha256`のkey/valueが不正です。"
            )

        path = raw_path.strip().replace("\\", "/")
        file_hash = raw_hash.strip()

        if path in normalized:
            raise StarterContractError(
                "`requiredAssetSha256`に重複パスがあります: "
                f"{path}"
            )

        validate_dist_asset_path(path)

        if not SHA256_PATTERN.fullmatch(file_hash):
            raise StarterContractError(
                f"asset SHA-256が不正です: {path}"
            )

        normalized[path] = file_hash

    required_set = set(required_assets)
    actual_set = set(normalized)

    if actual_set != required_set:
        missing = sorted(required_set - actual_set)
        unexpected = sorted(actual_set - required_set)

        raise StarterContractError(
            "`requiredAssetSha256`と`requiredAssets`が"
            "一致しません。"
            f" missing={missing}"
            f" unexpected={unexpected}"
        )

    return normalized


def load_starter_contract(
    base_dir: Path,
) -> StarterContract:
    contract_path = contract_path_for(base_dir)

    if not contract_path.is_file():
        raise StarterContractError(
            "starter接続契約が見つかりません: "
            f"{contract_path}"
        )

    try:
        raw_data = json.loads(
            contract_path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise StarterContractError(
            "starter接続契約を読み込めません: "
            f"{error}"
        ) from error

    if not isinstance(raw_data, dict):
        raise StarterContractError(
            "starter接続契約のルートは"
            "objectである必要があります。"
        )

    schema_version = raw_data.get("schemaVersion")

    if schema_version != 1:
        raise StarterContractError(
            "未対応のstarter接続契約schemaVersionです。"
        )

    repository_name = raw_data.get("repositoryName")

    if (
        not isinstance(repository_name, str)
        or not repository_name.strip()
    ):
        raise StarterContractError(
            "`repositoryName`が不正です。"
        )

    repository_name = repository_name.strip()

    if (
        Path(repository_name).name
        != repository_name
        or repository_name in {".", ".."}
    ):
        raise StarterContractError(
            "`repositoryName`は単一ディレクトリ名にしてください。"
        )

    required_commit = raw_data.get("requiredCommit")

    if (
        not isinstance(required_commit, str)
        or not COMMIT_PATTERN.fullmatch(required_commit)
    ):
        raise StarterContractError(
            "`requiredCommit`は40文字の"
            "小文字SHAである必要があります。"
        )

    required_assets = require_string_list(
        raw_data,
        "requiredAssets",
    )

    for relative_path in required_assets:
        validate_dist_asset_path(relative_path)

    copied_dist_roots = require_string_list(
        raw_data,
        "copiedDistRoots",
    )

    for relative_path in copied_dist_roots:
        validate_dist_asset_path(relative_path)

    copied_parts = [
        PurePosixPath(path).parts
        for path in copied_dist_roots
    ]

    for index, left in enumerate(copied_parts):
        for right in copied_parts[index + 1:]:
            shorter = min(
                len(left),
                len(right),
            )

            if (
                left[:shorter]
                == right[:shorter]
            ):
                raise StarterContractError(
                    "copiedDistRootsは"
                    "重複・包含しない"
                    "ディレクトリを"
                    "指定してください。"
                )

    dist_tree_sha256 = require_sha256(
        raw_data,
        "distTreeSha256",
    )

    required_asset_sha256 = require_asset_hashes(
        raw_data,
        required_assets,
    )

    runtime_tokens = require_string_list(
        raw_data,
        "requiredRuntimeTokens",
    )

    return StarterContract(
        schema_version=schema_version,
        repository_name=repository_name,
        required_commit=required_commit,
        required_assets=required_assets,
        copied_dist_roots=copied_dist_roots,
        dist_tree_sha256=dist_tree_sha256,
        required_asset_sha256=required_asset_sha256,
        runtime_tokens=runtime_tokens,
    )


def run_git(
    repository_root: Path,
    *arguments: str,
) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or "詳細なし"
        )

        raise StarterContractError(
            "sass-starter-exigaのgit検査に"
            f"失敗しました: {detail}"
        )

    return result.stdout.strip()


def resolve_contract_asset(
    repository_root: Path,
    relative_path: str,
) -> Path:
    repository_root = repository_root.resolve()
    dist_root = (repository_root / "dist").resolve()

    candidate = repository_root.joinpath(
        *PurePosixPath(relative_path).parts
    ).resolve()

    try:
        candidate.relative_to(dist_root)
    except ValueError as error:
        raise StarterContractError(
            "dist外を参照するassetは禁止です: "
            f"{relative_path}"
        ) from error

    return candidate


def hash_dist_artifact_tree(
    repository_root: Path,
    copied_dist_roots: tuple[str, ...],
) -> dict[str, str | int]:
    repository_root = (
        repository_root.resolve()
    )
    dist_root = (
        repository_root
        / "dist"
    ).resolve()

    records: dict[str, Path] = {}

    for relative_root in (
        copied_dist_roots
    ):
        source_root = (
            repository_root.joinpath(
                *PurePosixPath(
                    relative_root
                ).parts
            ).resolve()
        )

        try:
            source_root.relative_to(
                dist_root
            )
        except ValueError as error:
            raise StarterContractError(
                "コピー対象rootがdist外を"
                "参照しています: "
                f"{relative_root}"
            ) from error

        if not source_root.is_dir():
            raise StarterContractError(
                "コピー対象rootが"
                "見つかりません: "
                f"{source_root}"
            )

        for path in source_root.rglob(
            "*"
        ):
            if not path.is_file():
                continue

            relative_path = (
                path.relative_to(
                    dist_root
                ).as_posix()
            )

            if relative_path in records:
                raise StarterContractError(
                    "コピー対象rootが"
                    "重複しています: "
                    f"{relative_path}"
                )

            records[
                relative_path
            ] = path

    if not records:
        raise StarterContractError(
            "コピー対象dist assetが"
            "ありません。"
        )

    digest = hashlib.sha256()

    for relative_path in sorted(
        records
    ):
        digest.update(
            relative_path.encode(
                "utf-8"
            )
        )
        digest.update(b"\0")

        with records[
            relative_path
        ].open("rb") as file:
            for chunk in iter(
                lambda: file.read(
                    1024 * 1024
                ),
                b"",
            ):
                digest.update(chunk)

        digest.update(b"\0")

    return {
        "sha256": digest.hexdigest(),
        "fileCount": len(records),
    }


def validate_starter_contract(
    base_dir: Path,
) -> ValidatedStarter:
    contract = load_starter_contract(base_dir)

    repository_root = (
        base_dir.parent
        / contract.repository_name
    ).resolve()

    if not repository_root.is_dir():
        raise StarterContractError(
            "sass-starter-exigaが見つかりません: "
            f"{repository_root}"
        )

    actual_head = run_git(
        repository_root,
        "rev-parse",
        "HEAD",
    )

    if actual_head != contract.required_commit:
        raise StarterContractError(
            "sass-starter-exigaのHEADが接続契約と"
            "一致しません。"
            f" expected={contract.required_commit}"
            f" actual={actual_head}"
        )

    status = run_git(
        repository_root,
        "status",
        "--short",
        "--untracked-files=all",
    )

    if status:
        raise StarterContractError(
            "sass-starter-exigaのworking treeが"
            "cleanではありません。"
        )

    dist_root = repository_root / "dist"

    if not dist_root.is_dir():
        raise StarterContractError(
            f"starter distが見つかりません: {dist_root}"
        )

    for relative_path in contract.required_assets:
        asset_path = resolve_contract_asset(
            repository_root,
            relative_path,
        )

        if not asset_path.is_file():
            raise StarterContractError(
                "接続契約で要求されたassetが"
                f"ありません: {asset_path}"
            )

        actual_asset_hash = sha256_file(asset_path)
        expected_asset_hash = (
            contract.required_asset_sha256[
                relative_path
            ]
        )

        if actual_asset_hash != expected_asset_hash:
            raise StarterContractError(
                "starter asset SHA-256が接続契約と"
                "一致しません。"
                f" path={relative_path}"
                f" expected={expected_asset_hash}"
                f" actual={actual_asset_hash}"
            )

    actual_tree = hash_dist_artifact_tree(
        repository_root,
        contract.copied_dist_roots,
    )
    actual_tree_hash = str(actual_tree["sha256"])

    if actual_tree_hash != contract.dist_tree_sha256:
        raise StarterContractError(
            "starter dist tree SHA-256が接続契約と"
            "一致しません。"
            f" expected={contract.dist_tree_sha256}"
            f" actual={actual_tree_hash}"
        )

    js_root = repository_root / "dist" / "js"
    js_files = sorted(js_root.rglob("*.js"))

    if not js_files:
        raise StarterContractError(
            f"検査対象JavaScriptがありません: {js_root}"
        )

    js_content = "\n".join(
        path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        for path in js_files
    )

    missing_tokens = [
        token
        for token in contract.runtime_tokens
        if token not in js_content
    ]

    if missing_tokens:
        raise StarterContractError(
            "sass-starter-exigaのdist/jsに"
            "必要なruntime tokenがありません: "
            + ", ".join(missing_tokens)
        )

    return ValidatedStarter(
        repository_root=repository_root,
        dist_root=dist_root,
        head=actual_head,
        contract=contract,
    )
