"""T10 评测集与评估脚本测试。"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from internal_kb_qa.rag_assesment.ragas_evaluate import (
    build_oracle_predictions,
    evaluate_predictions,
    load_eval_set,
    write_report,
)


class TestT10Evaluation(unittest.TestCase):
    def test_eval_set_contract(self):
        items = load_eval_set()
        self.assertGreaterEqual(len(items), 50)
        self.assertLessEqual(len(items), 100)
        self.assertEqual(len({item.id for item in items}), len(items))
        self.assertTrue(any(item.should_handoff for item in items))
        self.assertTrue(any(item.permission_probe for item in items))

    def test_oracle_metrics_pass_thresholds(self):
        items = load_eval_set()
        metrics, rows = evaluate_predictions(items, build_oracle_predictions(items))
        self.assertEqual(len(rows), len(items))
        self.assertGreaterEqual(metrics["auto_answer_rate"], 0.80)
        self.assertGreaterEqual(metrics["citation_rate"], 1.00)
        self.assertGreaterEqual(metrics["permission_isolation"], 1.00)
        self.assertGreaterEqual(metrics["handoff_rate"], 1.00)
        self.assertGreaterEqual(metrics["faithfulness"], 0.80)
        self.assertGreaterEqual(metrics["answer_relevancy"], 0.80)
        self.assertGreaterEqual(metrics["context_relevancy"], 0.70)
        self.assertGreaterEqual(metrics["context_recall"], 0.70)

    def test_report_generation(self):
        items = load_eval_set()
        metrics, rows = evaluate_predictions(items, build_oracle_predictions(items))
        output = Path(os.environ.get("TMP", ".")) / "t10_eval_report_test.md"
        write_report(output, "oracle", items, metrics, rows)
        text = output.read_text(encoding="utf-8")
        self.assertIn("评估报告（T10）", text)
        self.assertIn("RAGAS 忠实度", text)
        self.assertIn("internal_kb_qa/rag_assesment/eval_set.json", text)


if __name__ == "__main__":
    unittest.main()
