from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


SPLIT_ALIASES = {
    "train": "train",
    "training": "train",
    "val": "validation",
    "valid": "validation",
    "validation": "validation",
    "test": "test",
}


@dataclass(frozen=True)
class RelevanceLabel:
    job_id: str
    resume_id: str
    label: int
    split: str | None = None
    source: str | None = None
    notes: str | None = None


def load_relevance_labels(path: Path) -> list[RelevanceLabel]:
    labels: list[RelevanceLabel] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        job_id = str(payload["job_id"]).strip()
        resume_id = str(payload["resume_id"]).strip()
        label = int(payload["label"])
        if label < 0:
            raise ValueError(f"Label must be non-negative at {path}:{line_number}")
        split = normalize_split(payload.get("split"))
        labels.append(
            RelevanceLabel(
                job_id=job_id,
                resume_id=resume_id,
                label=label,
                split=split,
                source=clean_optional_string(payload.get("source")),
                notes=clean_optional_string(payload.get("notes")),
            )
        )
    return labels


def build_label_lookup(labels: list[RelevanceLabel]) -> dict[tuple[str, str], RelevanceLabel]:
    lookup: dict[tuple[str, str], RelevanceLabel] = {}
    for label in labels:
        key = (label.job_id, label.resume_id)
        if key in lookup:
            raise ValueError(f"Duplicate relevance label for job_id={label.job_id} resume_id={label.resume_id}")
        lookup[key] = label
    return lookup


def default_split_for_job(job_id: str) -> str:
    bucket = hashlib.sha1(job_id.encode("utf-8")).digest()[0] / 255.0
    if bucket < 0.7:
        return "train"
    if bucket < 0.85:
        return "validation"
    return "test"


def summarize_labels(labels: list[RelevanceLabel]) -> dict[str, object]:
    split_counts: dict[str, int] = {}
    label_counts: dict[str, int] = {}
    for label in labels:
        split_name = label.split or "unspecified"
        split_counts[split_name] = split_counts.get(split_name, 0) + 1
        label_counts[str(label.label)] = label_counts.get(str(label.label), 0) + 1
    return {
        "label_count": len(labels),
        "job_count": len({label.job_id for label in labels}),
        "resume_count": len({label.resume_id for label in labels}),
        "split_counts": split_counts,
        "label_counts": label_counts,
    }


def normalize_split(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized not in SPLIT_ALIASES:
        raise ValueError(f"Unsupported label split: {value}")
    return SPLIT_ALIASES[normalized]


def clean_optional_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
