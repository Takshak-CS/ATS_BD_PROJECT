from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password}"
        )


@dataclass(frozen=True)
class ApiSettings:
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: tuple[str, ...] = ("*",)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def load_postgres_settings(env_file: Path | None) -> PostgresSettings:
    env_values = load_env_file(env_file) if env_file else {}

    def resolve(name: str, default: str | None = None) -> str:
        value = os.getenv(name, env_values.get(name, default))
        if value is None:
            raise RuntimeError(f"Missing required PostgreSQL setting: {name}")
        return value

    return PostgresSettings(
        host=resolve("POSTGRES_HOST", "localhost"),
        port=int(resolve("POSTGRES_PORT", "5432")),
        database=resolve("POSTGRES_DB"),
        user=resolve("POSTGRES_USER"),
        password=resolve("POSTGRES_PASSWORD"),
    )


def load_api_settings(env_file: Path | None) -> ApiSettings:
    env_values = load_env_file(env_file) if env_file else {}

    def resolve(name: str, default: str) -> str:
        return os.getenv(name, env_values.get(name, default))

    raw_origins = resolve("API_CORS_ORIGINS", "*")
    origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip()) or ("*",)
    return ApiSettings(
        host=resolve("API_HOST", "0.0.0.0"),
        port=int(resolve("API_PORT", "8000")),
        cors_origins=origins,
    )
