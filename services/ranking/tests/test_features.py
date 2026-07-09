from __future__ import annotations

import unittest

from ats_ranking.features import compute_education_match
from ats_ranking.features import compute_experience_alignment
from ats_ranking.features import compute_final_score
from ats_ranking.features import compute_role_relevance
from ats_ranking.features import compute_skill_coverage


PROFILE = {
    "education": [{"raw_text": "B.Tech in Computer Science"}],
    "experience": [{"raw_text": "Software Engineer 2019-2022", "date_range": "2019-2022"}],
    "projects": [{"raw_text": "Built REST APIs in Python"}],
    "raw_text": "Python SQL REST APIs Docker",
}


class RankingFeatureTests(unittest.TestCase):
    def test_skill_coverage(self) -> None:
        score = compute_skill_coverage(
            required_skills=["Python", "SQL"],
            preferred_skills=["Docker"],
            candidate_skills=["Python", "SQL"],
            candidate_text="Python SQL Docker",
        )
        self.assertGreaterEqual(score, 0.9)

    def test_experience_alignment(self) -> None:
        score = compute_experience_alignment("2-4 years", PROFILE)
        self.assertGreaterEqual(score, 1.0)

    def test_education_match(self) -> None:
        score = compute_education_match("Bachelor's degree in Computer Science", PROFILE)
        self.assertEqual(score, 1.0)

    def test_role_relevance(self) -> None:
        score = compute_role_relevance("Software Engineer", "Software engineer building backend APIs")
        self.assertGreater(score, 0.0)

    def test_final_score(self) -> None:
        score = compute_final_score(0.8, 0.9, 0.7, 1.0, 0.5)
        self.assertGreater(score, 0.75)


if __name__ == "__main__":
    unittest.main()
