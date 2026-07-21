from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from project_naming import normalize_project_display_name


MANIFEST_FILENAME = "project-manifest.json"


class GenerationManifestError(RuntimeError):
    pass


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def run_git_optional(
    repository_root: Path,
    *arguments: str,
) -> str | None:
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
        return None

    return result.stdout.strip()


def repository_state(
    repository_root: Path,
) -> dict[str, str | bool | None]:
    commit = run_git_optional(
        repository_root,
        "rev-parse",
        "HEAD",
    )

    if commit is None:
        return {
            "commit": None,
            "dirty": None,
        }

    status = run_git_optional(
        repository_root,
        "status",
        "--short",
        "--untracked-files=all",
    )

    return {
        "commit": commit,
        "dirty": (
            None
            if status is None
            else bool(status)
        ),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def hash_directory_tree(
    directory: Path,
) -> dict[str, str | int]:
    if not directory.is_dir():
        raise GenerationManifestError(
            f"hash対象ディレクトリがありません: {directory}"
        )

    files = sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
    )

    digest = hashlib.sha256()

    for path in files:
        relative_path = (
            path.relative_to(directory)
            .as_posix()
        )

        digest.update(
            relative_path.encode("utf-8")
        )
        digest.update(b"\0")

        with path.open("rb") as source:
            while True:
                chunk = source.read(1024 * 1024)

                if not chunk:
                    break

                digest.update(chunk)

        digest.update(b"\0")

    return {
        "algorithm": "sha256",
        "fileCount": len(files),
        "sha256": digest.hexdigest(),
    }


def required_asset_records(
    dist_root: Path,
    required_assets: Iterable[Path],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []

    for relative_path in required_assets:
        normalized_path = Path(relative_path)
        asset_path = (
            dist_root
            / normalized_path
        ).resolve()

        try:
            asset_path.relative_to(
                dist_root.resolve()
            )
        except ValueError as error:
            raise GenerationManifestError(
                "dist外を参照する必須assetは禁止です: "
                f"{relative_path}"
            ) from error

        if not asset_path.is_file():
            raise GenerationManifestError(
                f"必須assetがありません: {asset_path}"
            )

        records.append(
            {
                "path": (
                    "dist/"
                    + normalized_path.as_posix()
                ),
                "sha256": sha256_file(
                    asset_path
                ),
            }
        )

    return records


def read_generation_manifest(
    manifest_path: Path,
) -> dict[str, Any] | None:
    if not manifest_path.exists():
        return None

    if not manifest_path.is_file():
        raise GenerationManifestError(
            f"manifestがファイルではありません: {manifest_path}"
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
        raise GenerationManifestError(
            f"manifestを読み込めません: {error}"
        ) from error

    if not isinstance(data, dict):
        raise GenerationManifestError(
            "manifestのルートはobjectである必要があります。"
        )

    if data.get("schemaVersion") != 1:
        raise GenerationManifestError(
            "未対応のmanifest schemaVersionです。"
        )

    return data


def build_generation_manifest(
    *,
    base_dir: Path,
    starter_root: Path,
    dist_root: Path,
    template_name: str | None,
    project_name: str,
    project_slug: str,
    generated_date: str | None,
    operation: str,
    required_assets: Iterable[Path],
    existing_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = utc_timestamp()

    previous_created_at = (
        existing_manifest.get("createdAt")
        if existing_manifest
        else None
    )

    previous_generated_date = (
        existing_manifest.get("generatedDate")
        if existing_manifest
        else None
    )

    previous_project = (
        existing_manifest.get("project")
        if existing_manifest
        else None
    )

    if (
        template_name is None
        and isinstance(previous_project, dict)
    ):
        previous_template = previous_project.get(
            "template"
        )

        if isinstance(previous_template, str):
            template_name = previous_template

    resolved_project_name = (
        normalize_project_display_name(
            project_name
        )
    )

    if (
        operation == "refresh-dist"
        and isinstance(previous_project, dict)
    ):
        previous_project_name = (
            previous_project.get("name")
        )

        if (
            isinstance(
                previous_project_name,
                str,
            )
            and previous_project_name.strip()
        ):
            resolved_project_name = (
                previous_project_name
            )

    return {
        "schemaVersion": 1,
        "project": {
            "name": resolved_project_name,
            "slug": project_slug,
            "template": template_name,
        },
        "operation": operation,
        "generatedDate": (
            generated_date
            if generated_date is not None
            else previous_generated_date
        ),
        "createdAt": (
            previous_created_at
            if isinstance(previous_created_at, str)
            else timestamp
        ),
        "updatedAt": timestamp,
        "generator": {
            "repository": base_dir.name,
            **repository_state(base_dir),
        },
        "starter": {
            "repository": starter_root.name,
            **repository_state(starter_root),
        },
        "dist": {
            "tree": hash_directory_tree(
                dist_root
            ),
            "requiredAssets": (
                required_asset_records(
                    dist_root,
                    required_assets,
                )
            ),
        },
    }


def write_generation_manifest(
    manifest_path: Path,
    *,
    base_dir: Path,
    starter_root: Path,
    dist_root: Path,
    template_name: str | None,
    project_name: str,
    project_slug: str,
    generated_date: str | None,
    operation: str,
    required_assets: Iterable[Path],
    existing_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = build_generation_manifest(
        base_dir=base_dir,
        starter_root=starter_root,
        dist_root=dist_root,
        template_name=template_name,
        project_name=project_name,
        project_slug=project_slug,
        generated_date=generated_date,
        operation=operation,
        required_assets=required_assets,
        existing_manifest=existing_manifest,
    )

    manifest_path.write_text(
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
