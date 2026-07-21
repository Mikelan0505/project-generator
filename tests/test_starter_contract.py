from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import script
from generation_manifest import sha256_file
from starter_contract import (
    StarterContractError,
    hash_dist_artifact_tree,
    load_starter_contract,
    validate_starter_contract,
)


RUNTIME_TOKENS = [
    ".js-nav-toggle",
    "#site-nav",
    ".js-nav-overlay",
    ".js-reveal",
    "data-open",
]


class StarterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.temporary_directory.name
        )
        self.base_dir = (
            self.root
            / "project-generator"
        )
        self.starter_dir = (
            self.root
            / "sass-starter-exiga"
        )
        self.dist_root = (
            self.starter_dir
            / "dist"
        )

        self.base_dir.mkdir()
        self.starter_dir.mkdir()

        css_path = (
            self.dist_root
            / "css"
            / "main.css"
        )
        js_path = (
            self.dist_root
            / "js"
            / "core"
            / "app.js"
        )

        css_path.parent.mkdir(
            parents=True
        )
        js_path.parent.mkdir(
            parents=True
        )

        css_path.write_text(
            "/* starter css */\n",
            encoding="utf-8",
        )
        js_path.write_text(
            "\n".join(
                (
                    "const runtimeToken"
                    f"{index} = "
                    f"{json.dumps(token)};"
                )
                for index, token
                in enumerate(
                    RUNTIME_TOKENS
                )
            )
            + "\n",
            encoding="utf-8",
        )

        (
            self.starter_dir
            / ".gitignore"
        ).write_text(
            "dist/\n",
            encoding="utf-8",
        )
        (
            self.starter_dir
            / "README.md"
        ).write_text(
            "# fixture\n",
            encoding="utf-8",
        )

        self.run_git("init")
        self.run_git(
            "config",
            "user.name",
            "Generator Tests",
        )
        self.run_git(
            "config",
            "user.email",
            "generator-tests@example.invalid",
        )
        self.run_git(
            "add",
            ".gitignore",
            "README.md",
        )
        self.run_git(
            "commit",
            "-m",
            "fixture",
        )

        self.starter_head = self.run_git(
            "rev-parse",
            "HEAD",
        )

        self.write_contract()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_git(
        self,
        *arguments: str,
    ) -> str:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(self.starter_dir),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            self.fail(
                result.stderr.strip()
                or result.stdout.strip()
            )

        return result.stdout.strip()

    def asset_hashes(
        self,
        assets: list[str],
    ) -> dict[str, str]:
        result: dict[str, str] = {}

        for relative_path in assets:
            asset_path = (
                self.starter_dir
                / relative_path
            )

            result[relative_path] = (
                sha256_file(asset_path)
                if asset_path.is_file()
                else "0" * 64
            )

        return result

    def artifact_tree_hash(
        self,
    ) -> str:
        tree = hash_dist_artifact_tree(
            self.starter_dir,
            (
                "dist/css",
                "dist/js",
            ),
        )

        return str(tree["sha256"])

    def write_contract(
        self,
        *,
        required_commit: str | None = None,
        required_assets: list[str] | None = None,
        runtime_tokens: list[str] | None = None,
        dist_tree_sha256: str | None = None,
        required_asset_sha256: (
            dict[str, str] | None
        ) = None,
    ) -> None:
        assets = (
            required_assets
            if required_assets is not None
            else [
                "dist/css/main.css",
                "dist/js/core/app.js",
            ]
        )

        data = {
            "schemaVersion": 1,
            "repositoryName": (
                "sass-starter-exiga"
            ),
            "requiredCommit": (
                required_commit
                if required_commit is not None
                else self.starter_head
            ),
            "requiredAssets": assets,
            "requiredRuntimeTokens": (
                runtime_tokens
                if runtime_tokens is not None
                else RUNTIME_TOKENS
            ),
            "copiedDistRoots": [
                "dist/css",
                "dist/js",
            ],
            "distTreeSha256": (
                dist_tree_sha256
                if dist_tree_sha256 is not None
                else self.artifact_tree_hash()
            ),
            "requiredAssetSha256": (
                required_asset_sha256
                if required_asset_sha256
                is not None
                else self.asset_hashes(
                    assets
                )
            ),
        }

        (
            self.base_dir
            / "starter-contract.json"
        ).write_text(
            json.dumps(
                data,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_matching_contract_is_valid(
        self,
    ) -> None:
        contract = load_starter_contract(
            self.base_dir
        )
        validated = validate_starter_contract(
            self.base_dir
        )

        self.assertEqual(
            self.starter_head,
            contract.required_commit,
        )
        self.assertEqual(
            (
                "dist/css",
                "dist/js",
            ),
            contract.copied_dist_roots,
        )
        self.assertEqual(
            self.artifact_tree_hash(),
            contract.dist_tree_sha256,
        )
        self.assertEqual(
            self.starter_head,
            validated.head,
        )
        self.assertEqual(
            self.dist_root.resolve(),
            validated.dist_root.resolve(),
        )

    def test_wrong_commit_is_rejected(
        self,
    ) -> None:
        self.write_contract(
            required_commit="0" * 40,
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "HEAD",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_dirty_starter_is_rejected(
        self,
    ) -> None:
        (
            self.starter_dir
            / "README.md"
        ).write_text(
            "# dirty\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "clean",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_missing_asset_is_rejected(
        self,
    ) -> None:
        assets = [
            "dist/css/main.css",
            "dist/js/core/app.js",
            "dist/css/missing.css",
        ]

        self.write_contract(
            required_assets=assets,
            required_asset_sha256=(
                self.asset_hashes(
                    assets
                )
            ),
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "asset",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_missing_runtime_token_is_rejected(
        self,
    ) -> None:
        self.write_contract(
            runtime_tokens=[
                *RUNTIME_TOKENS,
                ".js-missing-hook",
            ],
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "js-missing-hook",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_runtime_token_substrings_are_rejected(
        self,
    ) -> None:
        js_path = (
            self.dist_root
            / "js"
            / "core"
            / "app.js"
        )
        js_path.write_text(
            "\n".join(
                (
                    "const misleadingToken"
                    f"{index} = "
                    f"{json.dumps(token + '-extra')};"
                )
                for index, token
                in enumerate(
                    RUNTIME_TOKENS
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_contract()

        with self.assertRaisesRegex(
            StarterContractError,
            re.escape(
                RUNTIME_TOKENS[0]
            ),
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_runtime_tokens_in_comments_are_rejected(
        self,
    ) -> None:
        js_path = (
            self.dist_root
            / "js"
            / "core"
            / "app.js"
        )
        js_path.write_text(
            "\n".join(
                (
                    "// inactive runtime token "
                    + json.dumps(token)
                )
                for token in RUNTIME_TOKENS
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_contract()

        with self.assertRaisesRegex(
            StarterContractError,
            re.escape(
                RUNTIME_TOKENS[0]
            ),
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_ignored_required_asset_change_is_rejected(
        self,
    ) -> None:
        (
            self.dist_root
            / "css"
            / "main.css"
        ).write_text(
            "/* modified ignored dist */\n",
            encoding="utf-8",
        )

        self.assertEqual(
            "",
            self.run_git(
                "status",
                "--short",
                "--untracked-files=all",
            ),
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "asset SHA-256",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_ignored_non_required_copied_asset_is_rejected(
        self,
    ) -> None:
        (
            self.dist_root
            / "js"
            / "extra.js"
        ).write_text(
            "export const extra = true;\n",
            encoding="utf-8",
        )

        self.assertEqual(
            "",
            self.run_git(
                "status",
                "--short",
                "--untracked-files=all",
            ),
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "tree SHA-256",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_non_copied_dist_content_is_ignored(
        self,
    ) -> None:
        dev_path = (
            self.dist_root
            / "dev"
            / "preview.html"
        )
        dev_path.parent.mkdir(
            parents=True
        )
        dev_path.write_text(
            "<p>preview</p>\n",
            encoding="utf-8",
        )

        validated = validate_starter_contract(
            self.base_dir
        )

        self.assertEqual(
            self.starter_head,
            validated.head,
        )

    def test_required_asset_hash_mismatch_is_rejected(
        self,
    ) -> None:
        assets = [
            "dist/css/main.css",
            "dist/js/core/app.js",
        ]
        hashes = self.asset_hashes(
            assets
        )
        hashes[
            "dist/css/main.css"
        ] = "0" * 64

        self.write_contract(
            required_asset_sha256=hashes,
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "asset SHA-256",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_dist_traversal_paths_are_rejected(
        self,
    ) -> None:
        invalid_paths = [
            "dist/../README.md",
            "dist\\..\\README.md",
            "../dist/css/main.css",
            "/dist/css/main.css",
            "C:/dist/css/main.css",
        ]

        for invalid_path in invalid_paths:
            with self.subTest(
                invalid_path=invalid_path
            ):
                normalized = (
                    invalid_path.replace(
                        "\\",
                        "/",
                    )
                )

                self.write_contract(
                    required_assets=[
                        invalid_path
                    ],
                    required_asset_sha256={
                        normalized: "0" * 64
                    },
                )

                with self.assertRaisesRegex(
                    StarterContractError,
                    "dist",
                ):
                    load_starter_contract(
                        self.base_dir
                    )

    def test_script_resolves_validated_dist(
        self,
    ) -> None:
        resolved_dist = (
            script.resolve_exiga_dist(
                self.base_dir
            )
        )

        self.assertEqual(
            self.dist_root.resolve(),
            resolved_dist.resolve(),
        )


if __name__ == "__main__":
    unittest.main()
