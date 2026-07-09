from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from ats_embedding.models import JobDescription

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - only exercised without dependency
    SentenceTransformer = None


DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingGenerator:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        if SentenceTransformer is None:
            raise RuntimeError(
                "Embedding generation requires sentence-transformers. "
                "Install the embedding service dependencies before running this service."
            )
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.astype("float32")


def build_candidate_embedding_text(profile_row: dict[str, Any]) -> str:
    profile = profile_row["profile_json"]
    parts: list[str] = []

    if profile_row.get("name"):
        parts.append(f"Candidate: {profile_row['name']}")
    if profile_row.get("skills"):
        parts.append("Skills: " + ", ".join(profile_row["skills"]))

    experience_entries = [entry["raw_text"] for entry in profile.get("experience", []) if entry.get("raw_text")]
    if experience_entries:
        parts.append("Experience: " + " ".join(experience_entries))

    project_entries = [entry["raw_text"] for entry in profile.get("projects", []) if entry.get("raw_text")]
    if project_entries:
        parts.append("Projects: " + " ".join(project_entries))

    education_entries = [entry["raw_text"] for entry in profile.get("education", []) if entry.get("raw_text")]
    if education_entries:
        parts.append("Education: " + " ".join(education_entries))

    achievements = profile.get("sections", {}).get("achievements")
    if achievements:
        parts.append("Achievements: " + achievements)

    if not parts:
        parts.append(profile.get("raw_text", ""))

    return "\n".join(part for part in parts if part).strip()


def build_job_embedding_text(job: JobDescription) -> str:
    parts = [
        f"Job Title: {job.job_title}",
        f"About: {job.about}" if job.about else None,
        "Responsibilities: " + " ".join(job.responsibilities) if job.responsibilities else None,
        "Required Skills: " + ", ".join(job.required_skills) if job.required_skills else None,
        "Preferred Skills: " + ", ".join(job.preferred_skills) if job.preferred_skills else None,
        f"Education: {job.education}" if job.education else None,
        "Good Fit: " + " ".join(job.good_fit_indicators) if job.good_fit_indicators else None,
    ]
    return "\n".join(part for part in parts if part).strip()


def compute_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_serializable_vector(vector: np.ndarray) -> list[float]:
    return vector.astype(float).tolist()


def write_json(path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
