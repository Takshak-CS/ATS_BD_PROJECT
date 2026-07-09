from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ats_ranking.evaluation import evaluate_ranker
from ats_ranking.evaluation import ndcg_at_k
from ats_ranking.labels import build_label_lookup
from ats_ranking.labels import default_split_for_job
from ats_ranking.labels import load_relevance_labels
from ats_ranking.signals import apply_business_rules
from ats_ranking.signals import compute_parser_quality_score


class RankingEvaluationTests(unittest.TestCase):
    def test_ndcg_perfect_ranking_is_one(self) -> None:
        self.assertEqual(ndcg_at_k([3, 2, 1, 0], 10), 1.0)

    def test_evaluate_ranker_reports_expected_metrics(self) -> None:
        rows = [
            {
                "job_id": "job_a",
                "job_title": "Job A",
                "resume_id": "r1",
                "label": 3,
                "retrieval_rank": 1,
                "heuristic_score": 0.91,
            },
            {
                "job_id": "job_a",
                "job_title": "Job A",
                "resume_id": "r2",
                "label": 0,
                "retrieval_rank": 2,
                "heuristic_score": 0.5,
            },
            {
                "job_id": "job_a",
                "job_title": "Job A",
                "resume_id": "r3",
                "label": 1,
                "retrieval_rank": 3,
                "heuristic_score": 0.4,
            },
        ]

        report = evaluate_ranker(rows, score_field="heuristic_score", min_relevant_label=1)
        self.assertEqual(report["jobs_with_labels"], 1)
        self.assertEqual(report["precision_at_5"], 0.666667)
        self.assertEqual(report["recall_at_10"], 1.0)
        self.assertAlmostEqual(report["ndcg_at_10"], 0.982842, places=6)

    def test_label_loader_normalizes_splits(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "labels.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "job_id": "job_a",
                        "resume_id": "r1",
                        "label": 2,
                        "split": "val",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            labels = load_relevance_labels(path)

        lookup = build_label_lookup(labels)
        self.assertEqual(lookup[("job_a", "r1")].split, "validation")
        self.assertIn(default_split_for_job("job_a"), {"train", "validation", "test"})

    def test_business_rules_penalize_missing_required_skills_and_warnings(self) -> None:
        adjusted_score, penalty, reasons = apply_business_rules(
            0.62,
            {
                "required_skill_count": 3,
                "skill_coverage": 0.0,
                "warning_count": 4,
                "has_email": 0.0,
            },
        )
        self.assertLess(adjusted_score, 0.62)
        self.assertGreater(penalty, 0.0)
        self.assertIn("missing_required_skill_coverage", reasons)

    def test_parser_quality_score_drops_with_missing_fields(self) -> None:
        score = compute_parser_quality_score(
            warning_count=4,
            has_name=False,
            has_email=False,
            has_phone=False,
            skills_count=0,
            experience_count=0,
        )
        self.assertLess(score, 0.5)


if __name__ == "__main__":
    unittest.main()
