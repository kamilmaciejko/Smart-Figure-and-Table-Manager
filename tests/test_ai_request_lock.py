"""Verify the duplicate-request guard used by both Streamlit AI workflows."""

import ast
import unittest
from pathlib import Path


class AiRequestLockTests(unittest.TestCase):
    def test_sidebar_disables_ai_actions_while_a_request_is_running(self):
        source = Path("app.py").read_text(encoding="utf-8")
        self.assertIn('"ai_request_in_progress": False', source)
        self.assertIn('disabled=ai_request_in_progress', source)
        self.assertIn('disabled=not ai_ready or ai_request_in_progress', source)

    def test_each_review_workflow_releases_the_lock_even_on_failure(self):
        for path in (Path("src/full_rework.py"), Path("src/refresh_workflow.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            finalizers = [node.finalbody for node in ast.walk(tree) if isinstance(node, ast.Try)]
            self.assertTrue(
                any(
                    any(
                        isinstance(node, ast.Assign)
                        and any(
                            isinstance(target, ast.Attribute)
                            and target.attr == "ai_request_in_progress"
                            for target in node.targets
                        )
                        for node in finalizer
                    )
                    for finalizer in finalizers
                ),
                path,
            )


if __name__ == "__main__":
    unittest.main()
