from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import script
from starter_contract import (
    StarterContractError,
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
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.base_dir = self.root / "project-generator"
        self.starter_dir = self.root / "sass-starter-exiga"
        self.base_dir.mkdir()
        self.starter_dir.mkdir()

        css_path = (
            self.starter_dir
            / "dist"
            / "css"
            / "main.css"
        )
        js_path = (
            self.starter_dir
            / "dist"
            / "js"
            / "core"
            / "app.js"
        )

        css_path.parent.mkdir(parents=True)
        js_path.parent.mkdir(parents=True)

        css_path.write_text(
            "/* starter css */\n",
            encoding="utf-8",
        )
        js_path.write_text(
            "\n".join(RUNTIME_TOKENS) + "\n",
            encoding="utf-8",
        )

        self.run_git("init")
        self.run_git("config", "user.name", "Generator Tests")
        self.run_git(
            "config",
            "user.email",
            "generator-tests@example.invalid",
        )
        self.run_git("add", ".")
        self.run_git("commit", "-m", "fixture")

        self.starter_head = self.run_git(
            "rev-parse",
            "HEAD",
        )

        self.write_contract()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_git(self, *arguments: str) -> str:
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

    def write_contract(
        self,
        *,
        required_commit: str | None = None,
        required_assets: list[str] | None = None,
        runtime_tokens: list[str] | None = None,
    ) -> None:
        data = {
            "schemaVersion": 1,
            "repositoryName": "sass-starter-exiga",
            "requiredCommit": (
                required_commit
                if required_commit is not None
                else self.starter_head
            ),
            "requiredAssets": (
                required_assets
                if required_assets is not None
                else [
                    "dist/css/main.css",
                    "dist/js/core/app.js",
                ]
            ),
            "requiredRuntimeTokens": (
                runtime_tokens
                if runtime_tokens is not None
                else RUNTIME_TOKENS
            ),
        }

        (
            self.base_dir
            / "starter-contract.json"
        ).write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_matching_contract_is_valid(self) -> None:
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
            self.starter_head,
            validated.head,
        )
        self.assertEqual(
            self.starter_dir.resolve(),
            validated.repository_root,
        )
        self.assertEqual(
            (
                self.starter_dir
                / "dist"
            ).resolve(),
            validated.dist_root,
        )

    def test_wrong_commit_is_rejected(self) -> None:
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

    def test_dirty_starter_is_rejected(self) -> None:
        (
            self.starter_dir
            / "dist"
            / "css"
            / "main.css"
        ).write_text(
            "/* dirty */\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "clean",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_missing_asset_is_rejected(self) -> None:
        self.write_contract(
            required_assets=[
                "dist/css/main.css",
                "dist/js/core/app.js",
                "dist/css/missing.css",
            ],
        )

        with self.assertRaisesRegex(
            StarterContractError,
            "asset",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_missing_runtime_token_is_rejected(self) -> None:
        self.write_contract(
            runtime_tokens=[
                *RUNTIME_TOKENS,
                ".js-missing-hook",
            ],
        )

        with self.assertRaisesRegex(
            StarterContractError,
            ".js-missing-hook",
        ):
            validate_starter_contract(
                self.base_dir
            )

    def test_script_resolves_validated_dist(self) -> None:
        resolved_dist = script.resolve_exiga_dist(
            self.base_dir
        )

        self.assertEqual(
            (
                self.starter_dir
                / "dist"
            ).resolve(),
            resolved_dist,
        )


if __name__ == "__main__":
    unittest.main()
