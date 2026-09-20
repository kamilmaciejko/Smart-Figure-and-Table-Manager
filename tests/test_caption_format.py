import unittest

import pandas as pd

from src.caption_format import clean_caption_cell, clean_page, format_number_group
from src.ui_helpers import build_changed_captions


class CaptionFormatTests(unittest.TestCase):
    def test_missing_editor_values_do_not_become_caption_text(self):
        for value in (None, pd.NA, float("nan"), " NaN ", "None", "<NA>", " "):
            with self.subTest(value=value):
                self.assertEqual(clean_caption_cell(value), "")
        self.assertEqual(clean_caption_cell("  Model results  "), "Model results")

    def test_invalid_pages_do_not_crash_export(self):
        for value in (None, pd.NA, "inf", float("-inf"), "NaN", "invalid", 0, 1000000):
            with self.subTest(value=value):
                self.assertEqual(clean_page(value), "")
        self.assertEqual(clean_page("12.0"), 12)

    def test_group_separators(self):
        for separator, expected in (("–", "1–3"), (",", "1, 2, 3"), ("and", "1 and 2 and 3"), ("i", "1 i 2 i 3")):
            with self.subTest(separator=separator):
                self.assertEqual(format_number_group([1, 2, 3], separator), expected)

    def test_group_range_advances_next_caption_number(self):
        captions = pd.DataFrame([
            {"images_in_paragraph": 3, "caption_paragraph_idx": 1, "text": "Panels", "source": pd.NA},
            {"images_in_paragraph": 1, "caption_paragraph_idx": 3, "text": "Results", "source": None},
        ])
        settings = {"caption_label": "Figure", "multi_image_strategy": "separate", "multi_number_separator": "–"}
        changed = build_changed_captions(captions, settings)
        self.assertEqual([row["label"] for row in changed], ["Figure 1–3.", "Figure 4."])
        self.assertEqual([row["source"] for row in changed], ["", ""])


if __name__ == "__main__":
    unittest.main()
