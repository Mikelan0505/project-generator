from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import convert_to_wp
import script
from project_naming import (
    escape_project_html,
    normalize_project_display_name,
    sanitize_project_slug,
    sanitize_theme_name,
)


HTML_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <title>{{PROJECT}} | {{PAGE_TITLE}}</title>
  <meta
    name="description"
    content="{{PROJECT}}"
  />
</head>
<body>
  <main>{{PROJECT}} / {{DATE}}</main>
</body>
</html>
"""


class ProjectNamingTests(unittest.TestCase):
    def test_display_name_collapses_control_whitespace(self) -> None:
        self.assertEqual(
            "Sample Project Name",
            normalize_project_display_name(
                "  Sample\tProject\r\nName  "
            ),
        )

    def test_windows_reserved_names_are_prefixed(self) -> None:
        self.assertEqual(
            "project-CON",
            sanitize_project_slug("CON"),
        )
        self.assertEqual(
            "project-con.txt",
            sanitize_project_slug("con.txt"),
        )
        self.assertEqual(
            "project-LPT9",
            sanitize_project_slug("LPT9"),
        )

    def test_html_escape_prevents_markup_injection(self) -> None:
        self.assertEqual(
            (
                "A&amp;B &lt;Test&gt; "
                "&quot;Quote&quot; &#x27;Single&#x27;"
            ),
            escape_project_html(
                """A&B <Test> "Quote" 'Single'"""
            ),
        )

    def test_generator_uses_safe_slug_and_escaped_html(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            base_dir = root / "project-generator"
            template_dir = base_dir / "templates" / "lp"
            template_dir.mkdir(parents=True)

            (template_dir / "index.html").write_text(
                HTML_TEMPLATE,
                encoding="utf-8",
            )

            dist_root = (
                root
                / "sass-starter-exiga"
                / "dist"
            )
            (dist_root / "css").mkdir(parents=True)
            (dist_root / "js" / "core").mkdir(parents=True)

            (dist_root / "css" / "main.css").write_text(
                "/* css */\n",
                encoding="utf-8",
            )
            (
                dist_root
                / "js"
                / "core"
                / "app.js"
            ).write_text(
                "export {};\n",
                encoding="utf-8",
            )

            project_name = 'A&B <Test> "Quote"'

            output_dir = script.create_project(
                base_dir=base_dir,
                template_name="lp",
                project_name=project_name,
                force=True,
            )

            self.assertEqual(
                "A&B-Test-Quote",
                output_dir.name,
            )

            html = (
                output_dir
                / "index.html"
            ).read_text(encoding="utf-8")

            self.assertNotIn(
                "<Test>",
                html,
            )
            self.assertIn(
                (
                    "A&amp;B &lt;Test&gt; "
                    "&quot;Quote&quot;"
                ),
                html,
            )

    def test_theme_name_is_single_line_and_comment_safe(self) -> None:
        project_name = "Bad\r\nName */ \\1"

        self.assertEqual(
            "Bad Name * / \\1",
            sanitize_theme_name(project_name),
        )

        rendered = convert_to_wp.render_style_css(
            "/*\nTheme Name: Existing\n*/\n",
            project_name=project_name,
        )

        theme_lines = [
            line
            for line in rendered.splitlines()
            if line.startswith("Theme Name:")
        ]

        self.assertEqual(
            ["Theme Name: Bad Name * / \\1"],
            theme_lines,
        )

    def test_convert_uses_shared_windows_slug_rules(self) -> None:
        self.assertEqual(
            "project-AUX",
            convert_to_wp.sanitize_project_name("AUX"),
        )

        with self.assertRaises(
            convert_to_wp.ConversionError
        ):
            convert_to_wp.sanitize_project_name(
                "\r\n\t"
            )


if __name__ == "__main__":
    unittest.main()
