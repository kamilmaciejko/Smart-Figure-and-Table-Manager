import unittest
from unittest.mock import patch

from src.word_pages import WordPageDetectionError, detect_object_pages


class WordPageValidationTests(unittest.TestCase):
    def test_matching_object_pages_are_returned(self):
        rows = {"images": [{"index": 1, "page": 2}], "tables": []}
        with patch("src.word_pages._run_page_worker", return_value=rows):
            pages = detect_object_pages(b"mock document", expected_images=1, expected_tables=0)
        self.assertEqual(pages["images"]["page"].tolist(), [2])
        self.assertEqual(pages["tables"].columns.tolist(), ["index", "page"])

    def test_missing_or_mismatched_pages_block_export(self):
        for rows in ([], [{"index": 2, "page": 1}], [{"index": 1, "page": None}], [{"index": 1, "page": 0}]):
            with self.subTest(rows=rows):
                with patch("src.word_pages._run_page_worker", return_value={"images": rows, "tables": []}):
                    with self.assertRaises(WordPageDetectionError):
                        detect_object_pages(b"mock document", expected_images=1, expected_tables=0)


if __name__ == "__main__":
    unittest.main()
