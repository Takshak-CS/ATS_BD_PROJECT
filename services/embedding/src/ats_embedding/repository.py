from __future__ import annotations

import re
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ats_embedding import __version__
from ats_embedding.config import PostgresSettings
from ats_embedding.models import JobDescription
from ats_embedding.models import RetrievalResult

try:
    import psycopg
except ImportError:  # pragma: no cover - only exercised without dependency
    psycopg = None


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid PostgreSQL identifier: {value}")
    return value


class EmbeddingRepository:
    def __init__(self, settings: PostgresSettings, schema: str = "public") -> None:
        if psycopg is None:
            raise RuntimeError(
                "Embedding persistence requires psycopg. Install the embedding service "
                "dependencies before running this service."
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
        if connection.execute("SELECT to_regclass('public.candidate_profiles')").fetchone()["to_regclass"] is None:
            raise RuntimeError(
                "candidate_profiles does not exist. Run the parser persistence flow before the embedding service."
            )

        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.job_descriptions (
              job_id TEXT PRIMARY KEY,
              source_filename TEXT NOT NULL,
              source_path TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              job_title TEXT NOT NULL,
              location TEXT,
              employment_type TEXT,
              experience_required TEXT,
              required_skills TEXT[] NOT NULL DEFAULT '{{}}',
              preferred_skills TEXT[] NOT NULL DEFAULT '{{}}',
              education TEXT,
              raw_text TEXT NOT NULL,
              structured_json JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.candidate_profile_embeddings (
              resume_id TEXT PRIMARY KEY REFERENCES {self.schema}.candidate_profiles (resume_id) ON DELETE CASCADE,
              model_name TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              embedding DOUBLE PRECISION[] NOT NULL,
              embedding_dim INTEGER NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.job_description_embeddings (
              job_id TEXT PRIMARY KEY REFERENCES {self.schema}.job_descriptions (job_id) ON DELETE CASCADE,
              model_name TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              embedding DOUBLE PRECISION[] NOT NULL,
              embedding_dim INTEGER NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.schema}.job_candidate_retrievals (
              job_id TEXT NOT NULL REFERENCES {self.schema}.job_descriptions (job_id) ON DELETE CASCADE,
              resume_id TEXT NOT NULL REFERENCES {self.schema}.candidate_profiles (resume_id) ON DELETE CASCADE,
              model_name TEXT NOT NULL,
              retrieval_rank INTEGER NOT NULL,
              semantic_similarity DOUBLE PRECISION NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (job_id, resume_id)
            )
            """
        )

    def upsert_job_description(self, connection, job: JobDescription, content_sha256: str) -> None:
        connection.execute(
            f"""
            INSERT INTO {self.schema}.job_descriptions (
              job_id,
              source_filename,
              source_path,
              content_sha256,
              job_title,
              location,
              employment_type,
              experience_required,
              required_skills,
              preferred_skills,
              education,
              raw_text,
              structured_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE SET
              source_filename = EXCLUDED.source_filename,
              source_path = EXCLUDED.source_path,
              content_sha256 = EXCLUDED.content_sha256,
              job_title = EXCLUDED.job_title,
              location = EXCLUDED.location,
              employment_type = EXCLUDED.employment_type,
              experience_required = EXCLUDED.experience_required,
              required_skills = EXCLUDED.required_skills,
              preferred_skills = EXCLUDED.preferred_skills,
              education = EXCLUDED.education,
              raw_text = EXCLUDED.raw_text,
              structured_json = EXCLUDED.structured_json,
              updated_at = NOW()
            """,
            (
                job.job_id,
                job.source_filename,
                job.source_path,
                content_sha256,
                job.job_title,
                job.location,
                job.employment_type,
                job.experience_required,
                job.required_skills,
                job.preferred_skills,
                job.education,
                job.raw_text,
                Jsonb(job.to_dict()),
            ),
        )

    def fetch_candidate_profiles(self, connection) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT resume_id, name, email, phone, skills, experience_count, project_count, warning_count, profile_json
                FROM {self.schema}.candidate_profiles
                ORDER BY resume_id
                """
            ).fetchall()
        )

    def fetch_candidate_profile(self, connection, resume_id: str) -> dict | None:
        return connection.execute(
            f"""
            SELECT resume_id, name, email, phone, skills, experience_count, project_count, warning_count, profile_json
            FROM {self.schema}.candidate_profiles
            WHERE resume_id = %s
            """,
            (resume_id,),
        ).fetchone()

    def fetch_job_descriptions(self, connection) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT job_id, source_filename, source_path, job_title, location, employment_type,
                       experience_required, required_skills, preferred_skills, education, raw_text, structured_json
                FROM {self.schema}.job_descriptions
                ORDER BY job_id
                """
            ).fetchall()
        )

    def fetch_job_retrievals(self, connection, job_id: str) -> list[dict]:
        return list(
            connection.execute(
                f"""
                SELECT job_id, resume_id, retrieval_rank, semantic_similarity
                FROM {self.schema}.job_candidate_retrievals
                WHERE job_id = %s
                ORDER BY retrieval_rank, resume_id
                """,
                (job_id,),
            ).fetchall()
        )

    def upsert_candidate_embedding(
        self,
        connection,
        resume_id: str,
        model_name: str,
        content_sha256: str,
        embedding: list[float],
    ) -> None:
        connection.execute(
            f"""
            INSERT INTO {self.schema}.candidate_profile_embeddings (
              resume_id, model_name, content_sha256, embedding, embedding_dim, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (resume_id) DO UPDATE SET
              model_name = EXCLUDED.model_name,
              content_sha256 = EXCLUDED.content_sha256,
              embedding = EXCLUDED.embedding,
              embedding_dim = EXCLUDED.embedding_dim,
              updated_at = NOW()
            """,
            (resume_id, model_name, content_sha256, embedding, len(embedding)),
        )

    def upsert_job_embedding(
        self,
        connection,
        job_id: str,
        model_name: str,
        content_sha256: str,
        embedding: list[float],
    ) -> None:
        connection.execute(
            f"""
            INSERT INTO {self.schema}.job_description_embeddings (
              job_id, model_name, content_sha256, embedding, embedding_dim, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (job_id) DO UPDATE SET
              model_name = EXCLUDED.model_name,
              content_sha256 = EXCLUDED.content_sha256,
              embedding = EXCLUDED.embedding,
              embedding_dim = EXCLUDED.embedding_dim,
              updated_at = NOW()
            """,
            (job_id, model_name, content_sha256, embedding, len(embedding)),
        )

    def replace_retrievals(
        self,
        connection,
        job_id: str,
        model_name: str,
        retrievals: list[RetrievalResult],
    ) -> None:
        connection.execute(
            f"DELETE FROM {self.schema}.job_candidate_retrievals WHERE job_id = %s",
            (job_id,),
        )
        for retrieval in retrievals:
            connection.execute(
                f"""
                INSERT INTO {self.schema}.job_candidate_retrievals (
                  job_id, resume_id, model_name, retrieval_rank, semantic_similarity, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    retrieval.job_id,
                    retrieval.resume_id,
                    model_name,
                    retrieval.retrieval_rank,
                    retrieval.semantic_similarity,
                ),
            )
