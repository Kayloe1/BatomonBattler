"""report.py reads the run logs (the saved Chef run is the fixture)."""
import unittest
from pathlib import Path

import report

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "runs" / "2026-11-12-chef" / "run_20261112_090412.jsonl"


class Report(unittest.TestCase):
    def test_run_summary(self):
        s = report.summarize_run(report.load(LOG))
        self.assertEqual(s["trainer"], "Chef")
        self.assertTrue(s["ended"])
        self.assertEqual(s["battles"], 2)

    def test_log_without_a_battle_is_skipped(self):
        self.assertIsNone(report.summarize_run([{"kind": "stop", "why": "x"}]))

    def test_unseen_list_and_odds(self):
        rep = report.report([LOG])
        self.assertIn("never_seen", rep)
        self.assertTrue(rep["shop_offers"])
        self.assertTrue(rep["income"])


if __name__ == "__main__":
    unittest.main()
