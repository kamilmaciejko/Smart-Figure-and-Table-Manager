import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from src.ai_config import improve_list_rows, llm_list_request


def response(items):
    message = SimpleNamespace(content=json.dumps({"items": items}))
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class ListCaptionAiTests(unittest.TestCase):
    config = {"completion_kwargs": {"model": "mock/model"}, "supported_openai_params": ()}

    def test_splits_explicit_figure_group(self):
        result = [{
            "id": "group-1", "decision": "EDIT", "edit_type": "TEXT_CORRECTION",
            "suggestions": [
                {"position": 1, "text": "Sales chart"},
                {"position": 2, "text": "Profit chart"},
            ],
        }]
        items = [{
            "id": "group-1",
            "texts": [
                "Sales chart on the left and profit chart on the right",
                "Sales chart on the left and profit chart on the right",
            ],
        }]

        with patch("litellm.completion", return_value=response(result)):
            rows = llm_list_request(self.config, "figures", items, "English")

        self.assertEqual([row["suggested_text"] for row in rows], ["Sales chart", "Profit chart"])
        self.assertTrue(all(row["edit_type"] == "TEXT_CORRECTION" for row in rows))

    def test_rejects_incomplete_figure_split(self):
        original = "Sales chart on the left and profit chart on the right"
        result = [{
            "id": "group-1", "decision": "EDIT", "edit_type": "TEXT_CORRECTION",
            "suggestions": [
                {"position": 1, "text": original},
                {"position": 2, "text": "Profit chart"},
            ],
        }]
        items = [{"id": "group-1", "texts": [original, original]}]

        with patch("litellm.completion", return_value=response(result)):
            rows = llm_list_request(self.config, "figures", items, "English")

        self.assertEqual([row["suggested_text"] for row in rows], [original, original])
        self.assertTrue(all(row["edit_type"] == "UNRESOLVED" for row in rows))

    def test_removes_table_commentary(self):
        result = [{
            "id": "table-1", "decision": "EDIT", "edit_type": "REMOVE_COMMENTARY",
            "suggested_text": "Quarterly sales.",
        }]
        items = [{"id": "table-1", "text": "Quarterly sales. Sales increased strongly."}]

        with patch("litellm.completion", return_value=response(result)):
            rows = llm_list_request(self.config, "tables", items, "English")

        self.assertEqual(rows[0]["suggested_text"], "Quarterly sales.")
        self.assertEqual(rows[0]["edit_type"], "REMOVE_COMMENTARY")

    def test_preserves_original_text_for_comparison(self):
        source = pd.DataFrame([{"label": "Table 1.", "text": "Old text", "page": 2}])
        ai_rows = [{
            "id": "tables-0", "position": 1, "suggested_text": "New text",
            "decision": "EDIT", "edit_type": "TEXT_CORRECTION", "error": None,
        }]

        with patch("src.ai_config.llm_list_request", return_value=ai_rows):
            result = improve_list_rows(self.config, source, "tables", "English")

        self.assertEqual(result.loc[0, "original_text"], "Old text")
        self.assertEqual(result.loc[0, "text"], "New text")

    def test_non_text_table_suggestions_preserve_original(self):
        for suggestion in (None, 123, ["A caption"], {"text": "A caption"}):
            with self.subTest(suggestion=suggestion):
                result = [{"id": "table-1", "decision": "EDIT", "edit_type": "TEXT_CORRECTION", "suggested_text": suggestion}]
                with patch("litellm.completion", return_value=response(result)):
                    rows = llm_list_request(self.config, "tables", [{"id": "table-1", "text": "Original"}], "English")
                self.assertEqual(rows[0]["suggested_text"], "Original")
                self.assertEqual(rows[0]["edit_type"], "UNRESOLVED")

    def test_invalid_figure_positions_preserve_original(self):
        for position in (True, 1.5, "1"):
            with self.subTest(position=position):
                result = [{"id": "figure-1", "decision": "EDIT", "edit_type": "TEXT_CORRECTION", "suggestions": [{"position": position, "text": "New"}]}]
                with patch("litellm.completion", return_value=response(result)):
                    rows = llm_list_request(self.config, "figures", [{"id": "figure-1", "text": "Original"}], "English")
                self.assertEqual(rows[0]["suggested_text"], "Original")
                self.assertEqual(rows[0]["edit_type"], "UNRESOLVED")

    def test_overlong_split_preserves_entire_group(self):
        for texts in (("Too long a caption", "Profit"), ("Sales", "Too long a caption")):
            with self.subTest(texts=texts):
                result = [{
                    "id": "group-1", "decision": "EDIT", "edit_type": "TEXT_CORRECTION",
                    "suggestions": [{"position": index, "text": text} for index, text in enumerate(texts, start=1)],
                }]
                originals = ["Sales left, profit right"] * 2
                with patch("litellm.completion", return_value=response(result)):
                    rows = llm_list_request(self.config, "figures", [{"id": "group-1", "texts": originals, "max_characters": 10}], "English")
                self.assertEqual([row["suggested_text"] for row in rows], originals)
                self.assertEqual([row["edit_type"] for row in rows], ["UNRESOLVED"] * 2)

    def test_invalid_response_ids_do_not_overwrite_captions(self):
        valid = {"id": "table-1", "decision": "EDIT", "edit_type": "TEXT_CORRECTION", "suggested_text": "New"}
        for result in ([], [valid, valid], [{**valid, "id": "unexpected"}], [None]):
            with self.subTest(result=result):
                with patch("litellm.completion", return_value=response(result)):
                    rows = llm_list_request(self.config, "tables", [{"id": "table-1", "text": "Original"}], "English")
                self.assertEqual(rows[0]["suggested_text"], "Original")
                self.assertEqual(rows[0]["status"], "error")

    def test_failed_batch_retries_items_individually(self):
        items = [{"id": "one", "text": "First"}, {"id": "two", "text": "Second"}]
        first = response([{"id": "one", "decision": "EDIT", "edit_type": "TEXT_CORRECTION", "suggested_text": "Edited"}])
        with patch("litellm.completion", side_effect=[ValueError("bad batch"), ValueError("bad batch"), first, TimeoutError("offline")]) as completion:
            rows = llm_list_request(self.config, "tables", items, "English")
        self.assertEqual(completion.call_count, 4)
        self.assertEqual([row["suggested_text"] for row in rows], ["Edited", "Second"])
        self.assertEqual([row["status"] for row in rows], ["success", "error"])

    def test_ai_request_contains_text_only_and_does_not_mutate_input(self):
        source = pd.DataFrame([{"label": "Table 1.", "text": "Original", "page": 2, "image_bytes": b"private image"}])
        reply = response([{"id": "tables-0", "decision": "KEEP", "edit_type": "NO_CHANGE", "suggested_text": "Original"}])
        with patch("litellm.completion", return_value=reply) as completion:
            result = improve_list_rows(self.config, source, "tables", "English")
        payload = json.loads(completion.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(set(payload["items"][0]), {"id", "texts", "image_count", "shared_caption", "max_characters"})
        self.assertNotIn("original_text", source.columns)
        self.assertEqual(result.loc[0, "image_bytes"], b"private image")


if __name__ == "__main__":
    unittest.main()
