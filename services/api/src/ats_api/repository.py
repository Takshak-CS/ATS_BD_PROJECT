from __future__ import annotations

import re
from contextlib import contextmanager

from psycopg.rows import dict_row

from ats_api.config import PostgresSettings

try:
    import psycopg
except ImportError:  # pragma: no cover - only exercised without dependency
    psycopg = None


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid PostgreSQL identifier: {value}")
    return value


class ApiRepository:
    def __init__(self, settings: PostgresSettings, schema: str = "public") -> None:
        if psycopg is None:
            raise RuntimeError(
                "API database access requires psycopg. Install the API service "
                "dependencies before running this service."
            )
        self.settings = settings
        self.schema = validate_identifier(schema)

    @contextmanager
    def connect(self):
        connection = psycopg.connect(self.settings.dsn, row_factory=dict_row)
        try:
            yield connection
        finally:
            connection.close()

    def fetch_jobs(self, connection) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT job_id, source_filename, source_path, content_sha256, job_title, location,
                       employment_type, experience_required, required_skills, preferred_skills,
                       education, raw_text, structured_json, created_at, updated_at
                FROM {self.schema}.job_descriptions
                ORDER BY job_title, job_id
                """
            ).fetchall()
        )

    def fetch_job(self, connection, job_id: str) -> dict | None:
        return connection.execute(
            f"""
            SELECT job_id, source_filename, source_path, content_sha256, job_title, location,
                   employment_type, experience_required, required_skills, preferred_skills,
                   education, raw_text, structured_json, created_at, updated_at
            FROM {self.schema}.job_descriptions
            WHERE job_id = %s
            """,
            (job_id,),
        ).fetchone()

    def fetch_job_rankings(self, connection, job_id: str) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT r.job_id, r.resume_id, r.retrieval_rank, r.ranking_rank,
                       r.semantic_similarity, r.skill_coverage, r.experience_alignment,
                       r.education_match, r.role_relevance, r.final_score, r.score_breakdown,
                       r.created_at, r.updated_at,
                       c.name, c.email, c.phone, c.skills,
                       c.education_count, c.experience_count, c.project_count, c.warning_count
                FROM {self.schema}.job_candidate_rankings r
                JOIN {self.schema}.candidate_profiles c ON c.resume_id = r.resume_id
                WHERE r.job_id = %s
                ORDER BY r.ranking_rank, r.resume_id
                """,
                (job_id,),
            ).fetchall()
        )

    def fetch_ranking_detail(self, connection, job_id: str, resume_id: str) -> dict | None:
        return connection.execute(
            f"""
            SELECT r.job_id, r.resume_id, r.retrieval_rank, r.ranking_rank,
                   r.semantic_similarity, r.skill_coverage, r.experience_alignment,
                   r.education_match, r.role_relevance, r.final_score, r.score_breakdown,
                   r.created_at AS ranking_created_at, r.updated_at AS ranking_updated_at,
                   c.source_filename, c.source_path, c.source_sha256, c.parser_version, c.parsed_at,
                   c.name, c.email, c.phone, c.skills, c.education_count, c.experience_count,
                   c.project_count, c.warning_count, c.profile_json
            FROM {self.schema}.job_candidate_rankings r
            JOIN {self.schema}.candidate_profiles c ON c.resume_id = r.resume_id
            WHERE r.job_id = %s AND r.resume_id = %s
            """,
            (job_id, resume_id),
        ).fetchone()
