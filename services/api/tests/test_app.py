from __future__ import annotations

import unittest
from contextlib import contextmanager

from ats_api.app import create_app
from starlette.requests import Request


class FakeApiRepository:
    @contextmanager
    def connect(self):
        yield None

    def fetch_jobs(self, connection) -> list[dict]:
        return [{"job_id": "software_engineer_jd_01", "job_title": "Software Engineer"}]

    def fetch_job(self, connection, job_id: str) -> dict | None:
        if job_id == "software_engineer_jd_01":
            return {"job_id": job_id, "job_title": "Software Engineer"}
        return None

    def fetch_job_rankings(self, connection, job_id: str) -> list[dict]:
        return [
            {
                "job_id": job_id,
                "resume_id": "c1",
                "ranking_rank": 1,
                "final_score": 0.91,
                "name": "Candidate One",
                "email": "candidate@example.com",
            }
        ]

    def fetch_ranking_detail(self, connection, job_id: str, resume_id: str) -> dict | None:
        if job_id != "software_engineer_jd_01" or resume_id != "c1":
            return None
        return {
            "job_id": job_id,
            "resume_id": resume_id,
            "retrieval_rank": 2,
            "ranking_rank": 1,
            "semantic_similarity": 0.82,
            "skill_coverage": 0.9,
            "experience_alignment": 0.8,
            "education_match": 1.0,
            "role_relevance": 0.5,
            "final_score": 0.91,
            "score_breakdown": {"semantic_similarity": 0.82},
            "ranking_created_at": "2026-04-01T00:00:00+00:00",
            "ranking_updated_at": "2026-04-01T00:00:00+00:00",
            "source_filename": "c1.pdf",
            "source_path": "data/raw/resumes/c1.pdf",
            "source_sha256": "abc",
            "parser_version": "0.1.0",
            "parsed_at": "2026-04-01T00:00:00+00:00",
            "name": "Candidate One",
            "email": "candidate@example.com",
            "phone": "1234567890",
            "skills": ["Python"],
            "education_count": 1,
            "experience_count": 1,
            "project_count": 1,
            "warning_count": 0,
            "profile_json": {"skills": ["Python"]},
        }


class ApiAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(repository=FakeApiRepository())

    def test_jobs_endpoint(self) -> None:
        payload = self.call_route("/jobs")
        self.assertEqual(payload["jobs"][0]["job_id"], "software_engineer_jd_01")

    def test_rankings_endpoint(self) -> None:
        payload = self.call_route("/jobs/{job_id}/rankings", "software_engineer_jd_01")
        self.assertEqual(payload["rankings"][0]["resume_id"], "c1")

    def test_ranking_detail_endpoint(self) -> None:
        payload = self.call_route("/jobs/{job_id}/rankings/{resume_id}", "software_engineer_jd_01", "c1")
        self.assertEqual(payload["candidate_profile"]["name"], "Candidate One")
        self.assertEqual(payload["ranking"]["ranking_rank"], 1)

    def call_route(self, path: str, *args):
        route = next(route for route in self.app.routes if getattr(route, "path", None) == path)
        request = Request(
            {
                "type": "http",
                "app": self.app,
                "headers": [],
                "method": "GET",
                "path": path,
                "query_string": b"",
            }
        )
        return route.endpoint(*args, request)


if __name__ == "__main__":
    unittest.main()
