from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass
class EducationEntry:
    raw_text: str
    degree: str | None = None
    institution: str | None = None
    year: str | None = None
    score: str | None = None


@dataclass
class ExperienceEntry:
    raw_text: str
    title: str | None = None
    organization: str | None = None
    date_range: str | None = None
    description: str | None = None


@dataclass
class ProjectEntry:
    raw_text: str
    name: str | None = None
    description: str | None = None
    technologies: list[str] = field(default_factory=list)


@dataclass
class ExtractionMetadata:
    file_type: str
    source_sha256: str
    text_length: int
    warnings: list[str] = field(default_factory=list)
    spacy_model: str | None = None


@dataclass
class ResumeProfile:
    resume_id: str
    source_path: str
    source_filename: str
    parsed_at: str
    name: str | None
    email: str | None
    phone: str | None
    skills: list[str]
    education: list[EducationEntry]
    experience: list[ExperienceEntry]
    certifications: list[str]
    projects: list[ProjectEntry]
    sections: dict[str, str]
    raw_text: str
    metadata: ExtractionMetadata

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
