from __future__ import annotations

import re
from typing import Any


STOPWORDS = {
    "a",
    "an",
    "and",
    "engineer",
    "for",
    "in",
    "of",
    "or",
    "the",
    "to",
}
YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")
RANGE_PATTERN = re.compile(r"(\d+)\s*-\s*(\d+)\s*years?", re.IGNORECASE)
PLUS_PATTERN = re.compile(r"(\d+)\+\s*years?", re.IGNORECASE)


def normalize_text(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-z0-9+]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def tokenize(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if token and token not in STOPWORDS}


def compute_skill_coverage(
    required_skills: list[str],
    preferred_skills: list[str],
    candidate_skills: list[str],
    candidate_text: str,
) -> float:
    candidate_skill_set = {normalize_text(skill) for skill in candidate_skills if skill}
    candidate_text_norm = normalize_text(candidate_text)

    def has_skill(skill: str) -> bool:
        normalized = normalize_text(skill)
        return normalized in candidate_skill_set or normalized in candidate_text_norm

    required_score = _coverage(required_skills, has_skill)
    preferred_score = _coverage(preferred_skills, has_skill)

    if required_skills and preferred_skills:
        return round(0.7 * required_score + 0.3 * preferred_score, 6)
    if required_skills:
        return round(required_score, 6)
    if preferred_skills:
        return round(preferred_score, 6)
    return 0.5


def _coverage(skills: list[str], matcher) -> float:
    if not skills:
        return 0.0
    matches = sum(1 for skill in skills if matcher(skill))
    return matches / len(skills)


def parse_experience_requirement(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    if match := RANGE_PATTERN.search(value):
        return int(match.group(1)), int(match.group(2))
    if match := PLUS_PATTERN.search(value):
        number = int(match.group(1))
        return number, None
    return None, None


def estimate_candidate_experience_years(profile_json: dict[str, Any]) -> float:
    experience_entries = profile_json.get("experience", [])
    spans: list[float] = []
    for entry in experience_entries:
        date_text = (entry.get("date_range") or entry.get("raw_text") or "").lower()
        years = [int(match.group(0)) for match in YEAR_PATTERN.finditer(date_text)]
        if len(years) >= 2:
            span = max(years) - min(years)
            spans.append(float(max(span, 1)))
        elif len(years) == 1:
            spans.append(1.0)

    if spans:
        return min(sum(spans), 20.0)

    return float(len(experience_entries))


def compute_experience_alignment(job_experience_required: str | None, profile_json: dict[str, Any]) -> float:
    min_years, _ = parse_experience_requirement(job_experience_required)
    if min_years is None:
        return 0.5

    candidate_years = estimate_candidate_experience_years(profile_json)
    if candidate_years <= 0:
        return 0.0
    return round(min(candidate_years / max(min_years, 1), 1.0), 6)


def infer_education_level_from_text(value: str | None) -> int:
    if not value:
        return 0
    normalized = normalize_text(value)
    if "phd" in normalized or "doctorate" in normalized:
        return 4
    if "master" in normalized or "m tech" in normalized or "m tech" in normalized or "m e" in normalized:
        return 3
    if "bachelor" in normalized or "b tech" in normalized or "b e" in normalized or "dual degree" in normalized:
        return 2
    if "class xii" in normalized or "class x" in normalized or "secondary" in normalized:
        return 1
    return 0


def compute_education_match(job_education: str | None, profile_json: dict[str, Any]) -> float:
    job_level = infer_education_level_from_text(job_education)
    candidate_levels = [
        infer_education_level_from_text(entry.get("raw_text"))
        for entry in profile_json.get("education", [])
    ]
    candidate_level = max(candidate_levels, default=0)

    if job_level == 0:
        return 0.5 if candidate_level else 0.0
    if candidate_level >= job_level:
        return 1.0
    if candidate_level > 0:
        return 0.5
    return 0.0


def compute_role_relevance(job_title: str, candidate_text: str) -> float:
    title_tokens = tokenize(job_title)
    if not title_tokens:
        return 0.0
    candidate_tokens = tokenize(candidate_text)
    overlap = len(title_tokens & candidate_tokens)
    return round(overlap / len(title_tokens), 6)


def compute_final_score(
    semantic_similarity: float,
    skill_coverage: float,
    experience_alignment: float,
    education_match: float,
    role_relevance: float,
) -> float:
    return round(
        0.45 * semantic_similarity
        + 0.25 * skill_coverage
        + 0.15 * experience_alignment
        + 0.10 * education_match
        + 0.05 * role_relevance,
        6,
    )
