from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from typing import Any
from typing import Mapping

from ats_ranking.features import compute_education_match
from ats_ranking.features import compute_experience_alignment
from ats_ranking.features import compute_final_score
from ats_ranking.features import compute_role_relevance
from ats_ranking.features import compute_skill_coverage


MODEL_FEATURE_NAMES = (
    "semantic_similarity",
    "skill_coverage",
    "experience_alignment",
    "education_match",
    "role_relevance",
    "warning_count",
    "parser_quality_score",
    "education_count",
    "experience_count",
    "project_count",
    "skills_count",
    "has_name",
    "has_email",
    "has_phone",
    "required_skill_count",
    "preferred_skill_count",
)


@dataclass(frozen=True)
class RankingSignals:
    semantic_similarity: float
    skill_coverage: float
    experience_alignment: float
    education_match: float
    role_relevance: float
    heuristic_score: float
    warning_count: int
    parser_quality_score: float
    education_count: int
    experience_count: int
    project_count: int
    skills_count: int
    has_name: float
    has_email: float
    has_phone: float
    required_skill_count: int
    preferred_skill_count: int

    def to_score_breakdown(self) -> dict[str, float]:
        return {
            "semantic_similarity": self.semantic_similarity,
            "skill_coverage": self.skill_coverage,
            "experience_alignment": self.experience_alignment,
            "education_match": self.education_match,
            "role_relevance": self.role_relevance,
        }

    def to_feature_dict(self) -> dict[str, float | int]:
        payload = asdict(self)
        return {
            key: value
            for key, value in payload.items()
            if key != "heuristic_score"
        }


def compute_ranking_signals(job: dict[str, Any], candidate: dict[str, Any]) -> RankingSignals:
    profile = candidate["profile_json"]
    candidate_text = build_candidate_feature_text(candidate)
    warning_count = int(candidate.get("warning_count") or 0)
    education_count = int(candidate.get("education_count") or len(profile.get("education", [])))
    experience_count = int(candidate.get("experience_count") or len(profile.get("experience", [])))
    project_count = int(candidate.get("project_count") or len(profile.get("projects", [])))
    skills = [skill for skill in candidate.get("skills", []) if skill]
    skills_count = len(skills)
    skill_coverage = compute_skill_coverage(
        required_skills=job["required_skills"],
        preferred_skills=job["preferred_skills"],
        candidate_skills=skills,
        candidate_text=candidate_text,
    )
    experience_alignment = compute_experience_alignment(job["experience_required"], profile)
    education_match = compute_education_match(job["education"], profile)
    role_relevance = compute_role_relevance(job["job_title"], candidate_text)
    semantic_similarity = round(float(candidate["semantic_similarity"]), 6)
    heuristic_score = compute_final_score(
        semantic_similarity=semantic_similarity,
        skill_coverage=skill_coverage,
        experience_alignment=experience_alignment,
        education_match=education_match,
        role_relevance=role_relevance,
    )
    parser_quality_score = compute_parser_quality_score(
        warning_count=warning_count,
        has_name=bool(candidate.get("name")),
        has_email=bool(candidate.get("email")),
        has_phone=bool(candidate.get("phone")),
        skills_count=skills_count,
        experience_count=experience_count,
    )

    return RankingSignals(
        semantic_similarity=semantic_similarity,
        skill_coverage=skill_coverage,
        experience_alignment=experience_alignment,
        education_match=education_match,
        role_relevance=role_relevance,
        heuristic_score=heuristic_score,
        warning_count=warning_count,
        parser_quality_score=parser_quality_score,
        education_count=education_count,
        experience_count=experience_count,
        project_count=project_count,
        skills_count=skills_count,
        has_name=1.0 if candidate.get("name") else 0.0,
        has_email=1.0 if candidate.get("email") else 0.0,
        has_phone=1.0 if candidate.get("phone") else 0.0,
        required_skill_count=len(job.get("required_skills") or []),
        preferred_skill_count=len(job.get("preferred_skills") or []),
    )


def build_candidate_feature_text(candidate: dict[str, Any]) -> str:
    profile = candidate["profile_json"]
    parts: list[str] = []
    if candidate.get("skills"):
        parts.append(", ".join(candidate["skills"]))
    for collection_name in ("experience", "projects", "education"):
        for entry in profile.get(collection_name, []):
            if entry.get("raw_text"):
                parts.append(entry["raw_text"])
    if profile.get("raw_text"):
        parts.append(profile["raw_text"])
    return "\n".join(parts)


def compute_parser_quality_score(
    warning_count: int,
    has_name: bool,
    has_email: bool,
    has_phone: bool,
    skills_count: int,
    experience_count: int,
) -> float:
    score = 1.0
    score -= min(max(warning_count, 0), 5) * 0.08
    if not has_name:
        score -= 0.15
    if not has_email:
        score -= 0.10
    if not has_phone:
        score -= 0.05
    if skills_count == 0:
        score -= 0.10
    if experience_count == 0:
        score -= 0.05
    return round(max(score, 0.0), 6)


def apply_business_rules(
    base_score: float,
    feature_source: RankingSignals | Mapping[str, Any],
) -> tuple[float, float, list[str]]:
    penalty = 0.0
    reasons: list[str] = []
    required_skill_count = int(get_feature_value(feature_source, "required_skill_count", default=0))
    skill_coverage = float(get_feature_value(feature_source, "skill_coverage", default=0.0))
    warning_count = int(get_feature_value(feature_source, "warning_count", default=0))
    has_email = float(get_feature_value(feature_source, "has_email", default=1.0))

    if required_skill_count > 0 and skill_coverage <= 0.0:
        penalty += 0.08
        reasons.append("missing_required_skill_coverage")
    if warning_count >= 3:
        parser_penalty = min(0.06, 0.02 * (warning_count - 2))
        penalty += parser_penalty
        reasons.append("parser_warning_penalty")
    if has_email <= 0.0:
        penalty += 0.02
        reasons.append("missing_contact_email")

    adjusted_score = round(max(float(base_score) - penalty, 0.0), 6)
    return adjusted_score, round(penalty, 6), reasons


def get_feature_value(
    feature_source: RankingSignals | Mapping[str, Any],
    name: str,
    default: float | int,
) -> float | int:
    if isinstance(feature_source, RankingSignals):
        return getattr(feature_source, name, default)
    return feature_source.get(name, default)
