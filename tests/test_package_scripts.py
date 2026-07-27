from __future__ import annotations

import json
import unittest
from pathlib import Path


class PackageScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        package_path = (
            Path(__file__).resolve()
            .parents[1]
            / "package.json"
        )
        package = json.loads(
            package_path.read_text(
                encoding="utf-8"
            )
        )
        cls.scripts = package["scripts"]

    def test_sample_generation_commands_match_contract(
        self,
    ) -> None:
        self.assertEqual(
            (
                "python script.py --template website "
                "--project sample --force"
            ),
            self.scripts["generate:sample"],
        )
        self.assertEqual(
            (
                "npm run generate:sample && "
                'html-validate "outputs/sample/**/*.html"'
            ),
            self.scripts["lint:html:sample"],
        )

    def test_html_lint_orders_templates_before_sample(
        self,
    ) -> None:
        self.assertEqual(
            'html-validate "templates/**/*.html"',
            self.scripts["lint:html:templates"],
        )
        self.assertEqual(
            (
                "npm run lint:html:templates && "
                "npm run lint:html:sample"
            ),
            self.scripts["lint:html"],
        )

    def test_check_orders_html_before_python(
        self,
    ) -> None:
        self.assertEqual(
            (
                "python -m unittest discover "
                "-s tests -q"
            ),
            self.scripts["test:python"],
        )
        self.assertEqual(
            (
                "npm run lint:html && "
                "npm run test:python"
            ),
            self.scripts["check"],
        )


if __name__ == "__main__":
    unittest.main()
