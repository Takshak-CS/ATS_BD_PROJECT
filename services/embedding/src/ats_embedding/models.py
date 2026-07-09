from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any


@dataclass
class JobDescription:
    job_id: str
    source_filename: str
    source_path: str
    job_title: str
    location: str | None
    employment_type: str | None
    experience_required: str | None
    about: str | None
    responsibilities: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    education: str | None = None
    good_fit_indicators: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResult:
    job_id: str
    resume_id: str
    retrieval_rank: int
    semantic_similarity: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
