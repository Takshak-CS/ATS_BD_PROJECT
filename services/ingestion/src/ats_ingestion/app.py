from __future__ import annotations

import argparse
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Protocol

import uvicorn
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

from ats_ingestion.config import DEFAULT_ENV_FILE
from ats_ingestion.config import IngestionSettings
from ats_ingestion.config import load_ingestion_settings
from ats_ingestion.publisher import publish_resume_uploaded_event
from ats_ingestion.storage import LocalResumeStorage
from ats_ingestion.storage import StoredResume


class ResumeEventPublisher(Protocol):
    def publish(self, payload: dict[str, object]) -> None: ...


class KafkaResumeEventPublisher:
    def __init__(self, env_file: Path) -> None:
        self.env_file = env_file

    def publish(self, payload: dict[str, object]) -> None:
        publish_resume_uploaded_event(payload=payload, env_file=self.env_file)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ATS ingestion upload API.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    return parser


def create_app(
    settings: IngestionSettings | None = None,
    storage: LocalResumeStorage | None = None,
    publisher: ResumeEventPublisher | None = None,
    env_file: Path = DEFAULT_ENV_FILE,
) -> FastAPI:
    app_settings = settings or load_ingestion_settings(env_file)
    app = FastAPI(title="ATS Ingestion API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.storage = storage or LocalResumeStorage(app_settings.upload_dir)
    app.state.publisher = publisher or KafkaResumeEventPublisher(env_file)
    app.state.settings = app_settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/uploads/resumes")
    async def upload_resume(request: Request) -> dict[str, object]:
        settings = request.app.state.settings
        source_filename = normalize_source_filename(request.headers.get("x-filename"))
        if not source_filename:
            raise HTTPException(status_code=400, detail="Missing required x-filename header.")
        ensure_allowed_extension(source_filename, settings.allowed_extensions)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                parsed_content_length = int(content_length)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid content-length header.") from exc
            if parsed_content_length > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds the {settings.max_upload_bytes}-byte limit.",
                )

        content = await request.body()
        if not content:
            raise HTTPException(status_code=400, detail="Upload body is empty.")
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds the {settings.max_upload_bytes}-byte limit.",
            )

        resume_id_override = request.headers.get("x-resume-id")
        try:
            stored_resume = request.app.state.storage.store(
                source_filename=source_filename,
                content=content,
                resume_id=resume_id_override,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        uploaded_at = datetime.now(timezone.utc).isoformat()
        payload = build_uploaded_payload(stored_resume, uploaded_at)

        try:
            request.app.state.publisher.publish(payload)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"Failed to publish resume.uploaded event: {exc}",
            ) from exc

        return {
            **payload,
            "file_size_bytes": stored_resume.file_size_bytes,
        }

    return app


def build_uploaded_payload(stored_resume: StoredResume, uploaded_at: str) -> dict[str, object]:
    return {
        "resume_id": stored_resume.resume_id,
        "source_filename": stored_resume.source_filename,
        "source_path": stored_resume.source_path,
        "uploaded_at": uploaded_at,
    }


def normalize_source_filename(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    filename = Path(raw_value.strip()).name
    return filename or None


def ensure_allowed_extension(source_filename: str, allowed_extensions: tuple[str, ...]) -> None:
    suffix = Path(source_filename).suffix.lower()
    if suffix not in allowed_extensions:
        allowed = ", ".join(allowed_extensions)
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type for {source_filename}. Allowed: {allowed}.",
        )


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    env_file = args.env_file
    settings = load_ingestion_settings(env_file)
    if args.host:
        settings = IngestionSettings(
            host=args.host,
            port=settings.port,
            cors_origins=settings.cors_origins,
            upload_dir=settings.upload_dir,
            max_upload_bytes=settings.max_upload_bytes,
            allowed_extensions=settings.allowed_extensions,
        )
    if args.port is not None:
        settings = IngestionSettings(
            host=settings.host,
            port=args.port,
            cors_origins=settings.cors_origins,
            upload_dir=settings.upload_dir,
            max_upload_bytes=settings.max_upload_bytes,
            allowed_extensions=settings.allowed_extensions,
        )

    app = create_app(
        settings=settings,
        storage=LocalResumeStorage(settings.upload_dir),
        publisher=KafkaResumeEventPublisher(env_file),
        env_file=env_file,
    )
    uvicorn.run(app, host=settings.host, port=settings.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
