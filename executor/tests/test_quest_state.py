"""Smoke tests for quest_state — uses chain reads against bpeon's known state.

These assertions match the state observed 2026-07-27 (re-recorded from
the 2026-04-30 session-70 snapshot after bpeon's live state advanced —
Q49 was completed in play, unlocking Q50):
- Q48 ("Pipe Dream") completed
- Q49 ("Community Service") completed
- Q50 ("You Smelt It…") owned but blocked on objs_not_met

These are live-state snapshots: they fail when the account is played
past the recorded state. On failure, verify the progression is
monotonic (quest_state reads coherently) and re-record.

Run from the executor/ directory:
    .venv/bin/python -m unittest tests.test_quest_state
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


class TestQuestState(unittest.TestCase):
    ACCOUNT = "bpeon"

    @classmethod
    def setUpClass(cls):
        # Skip the whole class if the snapshot account isn't loaded — these
        # tests are state-snapshots against bpeon's chain state from session 70.
        try:
            server._get_account(cls.ACCOUNT)
        except Exception as e:
            raise unittest.SkipTest(f"{cls.ACCOUNT} not configured: {e}")

    def test_q48_completed(self):
        r = server.quest_state(48, account=self.ACCOUNT)
        self.assertEqual(r["state"], "completed")
        self.assertTrue(r["completed"])
        self.assertTrue(r["owned"])

    def test_q49_completed(self):
        r = server.quest_state(49, account=self.ACCOUNT)
        self.assertEqual(r["state"], "completed")
        self.assertTrue(r["completed"])
        self.assertTrue(r["owned"])

    def test_q50_active_blocked_objs_not_met(self):
        r = server.quest_state(50, account=self.ACCOUNT)
        self.assertEqual(r["state"], "active_blocked")
        self.assertTrue(r["owned"])
        self.assertFalse(r["completed"])
        self.assertEqual(r["revert_kind"], "objs_not_met")


if __name__ == "__main__":
    unittest.main()
