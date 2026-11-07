"""Smoke tests for get_expected_objective — pure catalog reads, no chain.

Run from the executor/ directory:
    .venv/bin/python -m unittest tests.test_expected_objective
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


class TestExpectedObjective(unittest.TestCase):
    def test_q48_pipe_dream(self):
        r = server.get_expected_objective(48)
        self.assertEqual(r["title"], "Pipe Dream")
        self.assertEqual(len(r["objectives"]), 1)
        o = r["objectives"][0]
        self.assertEqual(o["type"], "DROPTABLE_ITEM_TOTAL")
        self.assertEqual(o["index"], 1017)
        self.assertEqual(o["value"], 5)

    def test_q49_q50_at_the_pin(self):
        # Upstream 8fb6ea58 (the catalog pin since 5.0.1): Community
        # Service is quest 50 and quest 49 is You Smelt It… — the
        # 2026-05-01 copy this test was first written against had the two
        # titles the other way round.
        r = server.get_expected_objective(50)
        self.assertEqual(r["title"], "Community Service")
        self.assertEqual(len(r["objectives"]), 1)
        o = r["objectives"][0]
        self.assertEqual(o["type"], "DROPTABLE_ITEM_TOTAL")
        self.assertEqual(o["index"], 1018)
        self.assertEqual(o["value"], 15)

        r = server.get_expected_objective(49)
        self.assertEqual(r["title"], "You Smelt It…")
        self.assertEqual(len(r["objectives"]), 1)
        o = r["objectives"][0]
        self.assertEqual(o["type"], "CRAFT_ITEM")
        self.assertEqual(o["index"], 1303)
        self.assertEqual(o["value"], 1)

    def test_unknown_quest_returns_partial(self):
        r = server.get_expected_objective(999999)
        self.assertEqual(r["objectives"], [])
        self.assertIn("note", r)


if __name__ == "__main__":
    unittest.main()
