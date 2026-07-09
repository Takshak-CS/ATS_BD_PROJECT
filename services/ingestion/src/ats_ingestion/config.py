from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_UPLOAD_DIR = REPO_ROOT / "data" / "raw" / "uploads"


@dataclass(frozen=True)
class IngestionSettings:
    host: str = "0.0.0.0"
    port: int = 8010
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    upload_dir: Path = DEFAULT_UPLOAD_DIR
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_extensions: tuple[str, ...] = (".pdf", ".docx", ".txt")


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


def load_ingestion_settings(env_file: Path | None) -> IngestionSettings:
    env_values = load_env_file(env_file) if env_file else {}

    def resolve(name: str, default: str) -> str:
        return os.getenv(name, env_values.get(name, default))

    raw_origins = resolve("INGESTION_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    origins = tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip())
    raw_extensions = resolve("INGESTION_ALLOWED_EXTENSIONS", ".pdf,.docx,.txt")
    allowed_extensions = tuple(
        extension if extension.startswith(".") else f".{extension}"
        for extension in (item.strip().lower() for item in raw_extensions.split(","))
        if extension
    )

    return IngestionSettings(
        host=resolve("INGESTION_HOST", "0.0.0.0"),
        port=int(resolve("INGESTION_PORT", "8010")),
        cors_origins=origins or IngestionSettings.cors_origins,
        upload_dir=Path(resolve("INGESTION_UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR))).expanduser(),
        max_upload_bytes=int(resolve("INGESTION_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        allowed_extensions=allowed_extensions or IngestionSettings.allowed_extensions,
    )
