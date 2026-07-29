from __future__ import annotations

import unittest

from core import completion_context, completion_items, embedded_language


class EmbeddedLanguageTests(unittest.TestCase):
    def test_styling_field_is_css(self) -> None:
        self.assertEqual(embedded_language(".card {", "css"), "css")

    def test_script_and_style_blocks(self) -> None:
        self.assertEqual(
            embedded_language("<div></div><script>const value =", "html"),
            "javascript",
        )
        self.assertEqual(
            embedded_language("<style>\n.card { color:", "html"), "css"
        )
        self.assertEqual(
            embedded_language("<script>x()</script><p>", "html"), "html"
        )


class CompletionTests(unittest.TestCase):
    def test_anki_prefix_supports_filters_and_spaces(self) -> None:
        self.assertEqual(completion_context("<p>{{type:My F", "html"), ("anki", "type:My F"))

    def test_language_prefixes(self) -> None:
        self.assertEqual(completion_context(".card { font-s", "css"), ("css", "font-s"))
        self.assertEqual(
            completion_context("<script>document.queryS", "html"),
            ("javascript", "queryS"),
        )
        self.assertEqual(completion_context("<di", "html"), ("html", "di"))

    def test_field_completions_include_anki_variants(self) -> None:
        items = completion_items("anki", ["Front", "My Field"])
        self.assertIn("My Field", items)
        self.assertIn("#My Field", items)
        self.assertIn("/My Field", items)
        self.assertIn("cloze:My Field", items)
        self.assertIn("FrontSide", items)

    def test_language_completions_are_scoped(self) -> None:
        self.assertIn("font-size", completion_items("css", []))
        self.assertNotIn("font-size", completion_items("javascript", []))
        self.assertIn("querySelector", completion_items("javascript", []))


if __name__ == "__main__":
    unittest.main()
