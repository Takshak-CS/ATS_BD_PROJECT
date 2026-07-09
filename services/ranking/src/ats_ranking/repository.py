from __future__ import annotations

import re
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ats_ranking.config import PostgresSettings

try:
    import psycopg
except ImportError:  # pragma: no cover - only exercised without dependency
    psycopg = None


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid PostgreSQL identifier: {value}")
    return value


class RankingRepository:
    def __init__(self, settings: PostgresSettings, schema: str = "public") -> None:
        if psycopg is None:
            raise RuntimeError(
                "Ranking persistence requires psycopg. Install the ranking service dependencies before running this service."
            )
        self.settings = settings
        self.schema = validate_identifier(schema)

    @contextmanager
    def connect(self):
        connection = psycopg.connect(self.settings.dsn, row_factory=dict_row)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self, connection) -> None:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.job_candidate_rankings (
              job_id TEXT NOT NULL REFERENCES {self.schema}.job_descriptions (job_id) ON DELETE CASCADE,
              resume_id TEXT NOT NULL REFERENCES {self.schema}.candidate_profiles (resume_id) ON DELETE CASCADE,
              retrieval_rank INTEGER NOT NULL,
              ranking_rank INTEGER NOT NULL,
              semantic_similarity DOUBLE PRECISION NOT NULL,
              skill_coverage DOUBLE PRECISION NOT NULL,
              experience_alignment DOUBLE PRECISION NOT NULL,
              education_match DOUBLE PRECISION NOT NULL,
              role_relevance DOUBLE PRECISION NOT NULL,
              final_score DOUBLE PRECISION NOT NULL,
              score_breakdown JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (job_id, resume_id)
            )
            """
        )

    def fetch_jobs(self, connection) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT job_id, job_title, experience_required, required_skills, preferred_skills, education, structured_json
                FROM {self.schema}.job_descriptions
                ORDER BY job_id
                """
            ).fetchall()
        )

    def fetch_job(self, connection, job_id: str) -> dict | None:
        return connection.execute(
            f"""
            SELECT job_id, job_title, experience_required, required_skills, preferred_skills, education, structured_json
            FROM {self.schema}.job_descriptions
            WHERE job_id = %s
            """,
            (job_id,),
        ).fetchone()

    def fetch_job_ids_for_resume(self, connection, resume_id: str) -> list[str]:
        return [
            row["job_id"]
            for row in connection.execute(
                f"""
                SELECT DISTINCT job_id
                FROM {self.schema}.job_candidate_retrievals
                WHERE resume_id = %s
                ORDER BY job_id
                """,
                (resume_id,),
            ).fetchall()
        ]

    def fetch_retrieval_candidates(self, connection, job_id: str) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT r.job_id, r.resume_id, r.retrieval_rank, r.semantic_similarity,
                       c.name, c.email, c.phone, c.skills, c.education_count,
                       c.experience_count, c.project_count, c.warning_count, c.profile_json
                FROM {self.schema}.job_candidate_retrievals r
                JOIN {self.schema}.candidate_profiles c ON c.resume_id = r.resume_id
                WHERE r.job_id = %s
                ORDER BY r.retrieval_rank
                """,
                (job_id,),
            ).fetchall()
        )

    def replace_rankings(self, connection, job_id: str, rows: list[dict]) -> None:
        connection.execute(
            f"DELETE FROM {self.schema}.job_candidate_rankings WHERE job_id = %s",
            (job_id,),
        )
        for row in rows:
            connection.execute(
                f"""
                INSERT INTO {self.schema}.job_candidate_rankings (
                  job_id,
                  resume_id,
                  retrieval_rank,
                  ranking_rank,
                  semantic_similarity,
                  skill_coverage,
                  experience_alignment,
                  education_match,
                  role_relevance,
                  final_score,
                  score_breakdown,
                  created_at,
                  updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    row["job_id"],
                    row["resume_id"],
                    row["retrieval_rank"],
                    row["ranking_rank"],
                    row["semantic_similarity"],
                    row["skill_coverage"],
                    row["experience_alignment"],
                    row["education_match"],
                    row["role_relevance"],
                    row["final_score"],
                    Jsonb(row["score_breakdown"]),
                ),
            )
