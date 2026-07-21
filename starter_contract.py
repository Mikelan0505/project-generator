from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class StarterContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class StarterContract:
    schema_version: int
    repository_name: str
    required_commit: str
    required_assets: tuple[str, ...]
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
            isinstance(item, str) and item.strip()
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


def load_starter_contract(
    base_dir: Path,
) -> StarterContract:
    contract_path = contract_path_for(base_dir)

    if not contract_path.is_file():
        raise StarterContractError(
            f"starter接続契約が見つかりません: {contract_path}"
        )

    try:
        raw_data = json.loads(
            contract_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise StarterContractError(
            f"starter接続契約を読み込めません: {error}"
        ) from error

    if not isinstance(raw_data, dict):
        raise StarterContractError(
            "starter接続契約のルートはobjectである必要があります。"
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
        Path(repository_name).name != repository_name
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
            "`requiredCommit`は40文字の小文字SHAである必要があります。"
        )

    required_assets = require_string_list(
        raw_data,
        "requiredAssets",
    )
    runtime_tokens = require_string_list(
        raw_data,
        "requiredRuntimeTokens",
    )

    for relative_path in required_assets:
        if not relative_path.startswith("dist/"):
            raise StarterContractError(
                "requiredAssetsはdist配下だけを指定できます: "
                f"{relative_path}"
            )

    return StarterContract(
        schema_version=schema_version,
        repository_name=repository_name,
        required_commit=required_commit,
        required_assets=required_assets,
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
            "sass-starter-exigaのgit検査に失敗しました: "
            f"{detail}"
        )

    return result.stdout.strip()


def resolve_contract_asset(
    repository_root: Path,
    relative_path: str,
) -> Path:
    repository_root = repository_root.resolve()
    candidate = (
        repository_root
        / relative_path
    ).resolve()

    try:
        candidate.relative_to(repository_root)
    except ValueError as error:
        raise StarterContractError(
            "starter外を参照するassetは禁止です: "
            f"{relative_path}"
        ) from error

    return candidate


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
            "sass-starter-exigaのHEADが接続契約と一致しません。"
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
            "sass-starter-exigaのworking treeがcleanではありません。"
        )

    for relative_path in contract.required_assets:
        asset_path = resolve_contract_asset(
            repository_root,
            relative_path,
        )

        if not asset_path.is_file():
            raise StarterContractError(
                "接続契約で要求されたassetがありません: "
                f"{asset_path}"
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

    dist_root = repository_root / "dist"

    if not dist_root.is_dir():
        raise StarterContractError(
            f"starter distが見つかりません: {dist_root}"
        )

    return ValidatedStarter(
        repository_root=repository_root,
        dist_root=dist_root,
        head=actual_head,
        contract=contract,
    )
