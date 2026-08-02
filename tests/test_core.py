from __future__ import annotations

import unittest

from core import anki_completion_items


class CompletionTests(unittest.TestCase):
    def test_field_completions_include_anki_variants(self) -> None:
        items = anki_completion_items(["Front", "My Field"])
        self.assertIn("My Field", items)
        self.assertIn("#My Field", items)
        self.assertIn("/My Field", items)
        self.assertIn("cloze:My Field", items)
        self.assertIn("FrontSide", items)


if __name__ == "__main__":
    unittest.main()
