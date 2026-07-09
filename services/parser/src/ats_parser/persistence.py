from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime

from ats_parser import __version__
from ats_parser.config import PostgresSettings
from ats_parser.models import ResumeProfile

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    psycopg = None
    Jsonb = None


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid PostgreSQL identifier: {value}")
    return value


class PostgresProfileRepository:
    def __init__(self, settings: PostgresSettings) -> None:
        if psycopg is None or Jsonb is None:
            raise RuntimeError(
                "PostgreSQL persistence requires psycopg. Install the parser service "
                "dependencies before using --persist-postgres."
            )
        self.settings = settings
        self.schema = validate_identifier(settings.schema)
        self.table = validate_identifier(settings.table)

    @contextmanager
    def connect(self):
        connection = psycopg.connect(self.settings.dsn)
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
            CREATE TABLE IF NOT EXISTS {self.schema}.{self.table} (
              resume_id TEXT PRIMARY KEY,
              source_filename TEXT NOT NULL,
              source_path TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              parsed_at TIMESTAMPTZ NOT NULL,
              name TEXT,
              email TEXT,
              phone TEXT,
              skills TEXT[] NOT NULL DEFAULT '{{}}',
              education_count INTEGER NOT NULL DEFAULT 0,
              experience_count INTEGER NOT NULL DEFAULT 0,
              project_count INTEGER NOT NULL DEFAULT 0,
              warning_count INTEGER NOT NULL DEFAULT 0,
              profile_json JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.table}_email_idx
            ON {self.schema}.{self.table} (email)
            """
        )
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.table}_source_sha_idx
            ON {self.schema}.{self.table} (source_sha256)
            """
        )
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.table}_profile_json_gin
            ON {self.schema}.{self.table}
            USING GIN (profile_json)
            """
        )

    def upsert_profile(self, connection, profile: ResumeProfile) -> None:
        payload = profile.to_dict()
        connection.execute(
            f"""
            INSERT INTO {self.schema}.{self.table} (
              resume_id,
              source_filename,
              source_path,
              source_sha256,
              parser_version,
              parsed_at,
              name,
              email,
              phone,
              skills,
              education_count,
              experience_count,
              project_count,
              warning_count,
              profile_json
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (resume_id) DO UPDATE SET
              source_filename = EXCLUDED.source_filename,
              source_path = EXCLUDED.source_path,
              source_sha256 = EXCLUDED.source_sha256,
              parser_version = EXCLUDED.parser_version,
              parsed_at = EXCLUDED.parsed_at,
              name = EXCLUDED.name,
              email = EXCLUDED.email,
              phone = EXCLUDED.phone,
              skills = EXCLUDED.skills,
              education_count = EXCLUDED.education_count,
              experience_count = EXCLUDED.experience_count,
              project_count = EXCLUDED.project_count,
              warning_count = EXCLUDED.warning_count,
              profile_json = EXCLUDED.profile_json,
              updated_at = NOW()
            """,
            (
                profile.resume_id,
                profile.source_filename,
                profile.source_path,
                profile.metadata.source_sha256,
                __version__,
                datetime.fromisoformat(profile.parsed_at),
                profile.name,
                profile.email,
                profile.phone,
                profile.skills,
                len(profile.education),
                len(profile.experience),
                len(profile.projects),
                len(profile.metadata.warnings),
                Jsonb(payload),
            ),
        )
