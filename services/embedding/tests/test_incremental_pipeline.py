from __future__ import annotations

import unittest

from ats_embedding.pipeline import merge_candidate_into_retrievals


class IncrementalEmbeddingTests(unittest.TestCase):
    def test_candidate_enters_top_k(self) -> None:
        rows, changed = merge_candidate_into_retrievals(
            job_id="job_1",
            resume_id="c3",
            semantic_similarity=0.93,
            current_rows=[
                {"job_id": "job_1", "resume_id": "c1", "semantic_similarity": 0.91},
                {"job_id": "job_1", "resume_id": "c2", "semantic_similarity": 0.82},
            ],
            top_k=2,
        )

        self.assertTrue(changed)
        self.assertEqual([row["resume_id"] for row in rows], ["c3", "c1"])

    def test_candidate_below_top_k_is_ignored_when_not_present(self) -> None:
        rows, changed = merge_candidate_into_retrievals(
            job_id="job_1",
            resume_id="c3",
            semantic_similarity=0.1,
            current_rows=[
                {"job_id": "job_1", "resume_id": "c1", "semantic_similarity": 0.91},
                {"job_id": "job_1", "resume_id": "c2", "semantic_similarity": 0.82},
            ],
            top_k=2,
        )

        self.assertFalse(changed)
        self.assertEqual([row["resume_id"] for row in rows], ["c1", "c2"])

    def test_candidate_drop_out_still_marks_job_changed(self) -> None:
        rows, changed = merge_candidate_into_retrievals(
            job_id="job_1",
            resume_id="c2",
            semantic_similarity=0.2,
            current_rows=[
                {"job_id": "job_1", "resume_id": "c1", "semantic_similarity": 0.91},
                {"job_id": "job_1", "resume_id": "c2", "semantic_similarity": 0.82},
                {"job_id": "job_1", "resume_id": "c4", "semantic_similarity": 0.74},
            ],
            top_k=2,
        )

        self.assertTrue(changed)
        self.assertEqual([row["resume_id"] for row in rows], ["c1", "c4"])


if __name__ == "__main__":
    unittest.main()
