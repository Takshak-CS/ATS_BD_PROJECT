from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class StoredResume:
    resume_id: str
    source_filename: str
    source_path: str
    file_size_bytes: int


def sanitize_resume_id(value: str) -> str:
    cleaned = SAFE_ID_PATTERN.sub("-", value.strip()).strip("-_")
    if not cleaned:
        raise ValueError("Resume ID must contain at least one alphanumeric character.")
    return cleaned


def derive_resume_id(source_filename: str) -> str:
    return sanitize_resume_id(Path(source_filename).stem)


class LocalResumeStorage:
    def __init__(self, upload_dir: Path) -> None:
        self.upload_dir = upload_dir.expanduser().resolve()

    def store(self, source_filename: str, content: bytes, resume_id: str | None = None) -> StoredResume:
        original_name = Path(source_filename).name
        suffix = Path(original_name).suffix.lower()
        resolved_resume_id = sanitize_resume_id(resume_id) if resume_id else derive_resume_id(original_name)
        destination_path = self.upload_dir / f"{resolved_resume_id}{suffix}"
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(content)
        return StoredResume(
            resume_id=resolved_resume_id,
            source_filename=original_name,
            source_path=str(destination_path),
            file_size_bytes=len(content),
        )
