from __future__ import annotations

from pathlib import Path

from ats_embedding.models import JobDescription


SECTION_HEADERS = {
    "about the role": "about",
    "key responsibilities": "responsibilities",
    "required skills": "required_skills",
    "preferred skills": "preferred_skills",
    "education": "education",
    "good fit indicators": "good_fit_indicators",
}


def load_job_descriptions(jd_dir: Path) -> list[JobDescription]:
    return [parse_job_description(path) for path in sorted(jd_dir.glob("*.txt"))]


def parse_job_description(path: Path) -> JobDescription:
    raw_text = path.read_text(encoding="utf-8")
    lines = [line.rstrip() for line in raw_text.splitlines()]

    metadata: dict[str, str | None] = {
        "job_title": None,
        "location": None,
        "employment_type": None,
        "experience_required": None,
    }
    sections: dict[str, list[str]] = {value: [] for value in SECTION_HEADERS.values()}
    current_section: str | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("Job Title:"):
            metadata["job_title"] = line.split(":", 1)[1].strip()
            current_section = None
            continue
        if line.startswith("Location:"):
            metadata["location"] = line.split(":", 1)[1].strip()
            current_section = None
            continue
        if line.startswith("Employment Type:"):
            metadata["employment_type"] = line.split(":", 1)[1].strip()
            current_section = None
            continue
        if line.startswith("Experience Required:"):
            metadata["experience_required"] = line.split(":", 1)[1].strip()
            current_section = None
            continue

        normalized = line.rstrip(":").strip().lower()
        if normalized in SECTION_HEADERS:
            current_section = SECTION_HEADERS[normalized]
            continue

        if current_section is None:
            continue

        sections[current_section].append(strip_list_prefix(line))

    if not metadata["job_title"]:
        raise RuntimeError(f"Could not parse job title from {path}")

    return JobDescription(
        job_id=path.stem,
        source_filename=path.name,
        source_path=str(path),
        job_title=metadata["job_title"] or path.stem,
        location=metadata["location"],
        employment_type=metadata["employment_type"],
        experience_required=metadata["experience_required"],
        about=" ".join(sections["about"]).strip() or None,
        responsibilities=sections["responsibilities"],
        required_skills=sections["required_skills"],
        preferred_skills=sections["preferred_skills"],
        education=" ".join(sections["education"]).strip() or None,
        good_fit_indicators=sections["good_fit_indicators"],
        raw_text=raw_text.strip(),
    )


def strip_list_prefix(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("-"):
        return stripped[1:].strip()
    return stripped
