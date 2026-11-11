"""Heritage signals remain advisory and never gate human decisions."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app/services/api"))

from asante_api.ai.heritage import evaluate_heritage_relevance, heuristic_heritage_gate  # noqa: E402


class HeritageGateTests(unittest.TestCase):
    def test_african_story_signal_is_advisory(self):
        result = heuristic_heritage_gate({"title": "African folktale", "summary": "A community memory."})
        self.assertEqual(result["decision"], "attention")
        self.assertEqual(result["status"], "attention")

    def test_missing_or_non_african_keywords_do_not_auto_reject(self):
        for packet in ({"title": "A story from my grandmother"}, {"title": "Nordic legend"}, {"title": "History for sleep"}):
            with self.subTest(packet=packet):
                result = heuristic_heritage_gate(packet)
                self.assertNotEqual(result["decision"], "reject")
                self.assertEqual(result["status"], "attention")

    def test_provider_rejection_is_still_human_attention(self):
        with patch("asante_api.ai.heritage.ask_model", return_value={"decision": "reject", "reason": "Keywords missing"}):
            result = evaluate_heritage_relevance({"title": "A story"})
        self.assertEqual(result["decision"], "attention")
        self.assertEqual(result["status"], "attention")


if __name__ == "__main__":
    unittest.main()
