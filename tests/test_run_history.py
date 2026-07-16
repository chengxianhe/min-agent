from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class RunHistoryTest(unittest.TestCase):
    def test_lists_valid_records_and_isolates_corrupt_file(self) -> None:
        from min_agent.run_history import RunHistory

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = {
                "run_id": "new",
                "status": "completed",
                "user_goal": "goal",
                "started_at": "2026-01-02",
                "ended_at": "2026-01-03",
                "events": [
                    {
                        "run_id": "new",
                        "step": 1,
                        "phase": "final_answer",
                        "output": {"message": "done"},
                    }
                ],
            }
            (root / "new.json").write_text(json.dumps(data), encoding="utf-8")
            (root / "bad.json").write_text("{", encoding="utf-8")
            result = RunHistory(root).list_runs()

        self.assertEqual(result.load_error_count, 1)
        self.assertEqual(result.runs[0]["decision_model"], "unknown")
        self.assertEqual(result.runs[0]["final_answer"], "done")
