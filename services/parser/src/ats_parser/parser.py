from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path

import spacy
from spacy.language import Language

from ats_parser.models import EducationEntry
from ats_parser.models import ExperienceEntry
from ats_parser.models import ExtractionMetadata
from ats_parser.models import ProjectEntry
from ats_parser.models import ResumeProfile


BULLET_CHARS = "•●▪◦■*-\u2013\u2014§"
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_PATTERN = re.compile(r"(?:\+?\d[\d ()-]{8,}\d)")
YEAR_PATTERN = re.compile(
    r"\b(?:19|20)\d{2}(?:\s*(?:-|to|–)\s*(?:present|current|(?:19|20)\d{2}))?\b",
    re.IGNORECASE,
)
DATE_RANGE_PATTERN = re.compile(
    r"("
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[’']?\s*\d{2,4}\s*(?:-|–|to)\s*"
    r"(?:present|current|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*[’']?\s*\d{2,4})"
    r"|"
    r"(?:19|20)\d{2}\s*(?:-|–|to)\s*(?:present|current|(?:19|20)\d{2})"
    r")",
    re.IGNORECASE,
)
PAREN_DATE_RANGE_PATTERN = re.compile(r"\([^)]*(?:19|20)\d{2}[^)]*\)")
SCORE_PATTERN = re.compile(
    r"(?:CGPA|GPA|Marks Obtained|Score|Percentage|Percentile)\s*[:\-]?\s*[\d.]+(?:/\d+)?%?"
    r"|"
    r"\b\d+(?:\.\d+)?/\d+\b"
    r"|"
    r"\b\d+(?:\.\d+)?\s*%",
    re.IGNORECASE,
)
DEGREE_PATTERN = re.compile(
    r"\b("
    r"dual degree|b\.?\s?tech|m\.?\s?tech|b\.?\s?e\.?|m\.?\s?e\.?|bachelor|master|mba|mca|bca|"
    r"b\.?\s?sc|m\.?\s?sc|ph\.?d|doctorate|diploma|class xii|class x|"
    r"senior secondary|secondary|cbse|hsc|ssc"
    r")\b",
    re.IGNORECASE,
)
INSTITUTION_PATTERN = re.compile(
    r"("
    r"(?:IIT|IIIT|NIT)\s+[A-Z][A-Za-z]+"
    r"|"
    r"(?:[A-Z][A-Za-z.&'/-]*(?:\s+[A-Z][A-Za-z.&'/-]*){0,8}\s+"
    r"(?:University|Institute(?:\s+of\s+Technology)?|College|School|Academy|Polytechnic)"
    r"(?:,?\s*[A-Z][A-Za-z.&'/-]+){0,3})"
    r")"
)
BAD_NAME_TERMS = {
    "resume",
    "curriculum vitae",
    "academic profile",
    "academeic profile",
    "education",
    "skills",
    "email",
    "phone",
    "mobile",
    "address",
    "roll no",
    "dob",
}


SKILL_PATTERNS = {
    "ajax": "AJAX",
    "aws": "AWS",
    "azure": "Azure",
    "c#": "C#",
    "c++": "C++",
    "c": "C",
    "css": "CSS",
    "data analysis": "Data Analysis",
    "data structures": "Data Structures",
    "django": "Django",
    "docker": "Docker",
    "eclipse": "Eclipse",
    "faiss": "FAISS",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "git": "Git",
    "hadoop": "Hadoop",
    "html": "HTML",
    "information retrieval": "Information Retrieval",
    "java ee": "Java EE",
    "java": "Java",
    "javascript": "JavaScript",
    "kubernetes": "Kubernetes",
    "latex": "LaTeX",
    "linux": "Linux",
    "machine learning": "Machine Learning",
    "mapreduce": "MapReduce",
    "matlab": "MATLAB",
    "mongodb": "MongoDB",
    "mysql": "MySQL",
    "netbeans": "NetBeans",
    "nlp": "NLP",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "numpy": "NumPy",
    "opencv": "OpenCV",
    "pandas": "Pandas",
    "php": "PHP",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "probability and statistics": "Probability and Statistics",
    "python": "Python",
    "pytorch": "PyTorch",
    "react": "React",
    "redis": "Redis",
    "scikit-learn": "scikit-learn",
    "spark": "Spark",
    "spacy": "spaCy",
    "spring": "Spring",
    "sql": "SQL",
    "tableau": "Tableau",
    "tensorflow": "TensorFlow",
    "verilog": "Verilog",
    "web services": "Web Services",
    "windows": "Windows",
    "xml": "XML",
}
SKILL_REGEXES = {
    canonical: re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
    for alias, canonical in SKILL_PATTERNS.items()
}

SECTION_ALIASES = {
    "education": {
        "education",
        "academic profile",
        "academeic profile",
        "academic background",
        "academic qualification",
        "academic qualifications",
        "educational qualification",
        "qualification",
        "qualifications",
        "academic history",
        "education background",
        "studies"
    },
    "skills": {
        "skills",
        "technical",
        "technical skills",
        "skill set",
        "core competencies",
        "tools technologies",
        "tools and technologies",
        "software proficiency",
        "relevant courses taken",
        "expertise",
        "skills languages",
        "technical proficiencies"
    },
    "experience": {
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "work experience internship",
        "internship",
        "internships",
        "work history",
        "professional background",
        "career history",
        "relevant experience",
        "employment"
    },
    "projects": {
        "projects",
        "academic projects",
        "project experience",
        "research projects",
        "key projects",
        "selected projects",
        "personal projects",
        "technical projects",
        "contributions",
        "open source",
        "featured projects"
    },
    "certifications": {
        "qualification certificates",
        "certification",
        "certifications",
        "licenses",
        "licenses certifications",
        "courses certifications"
    },
    "achievements": {
        "achievements",
        "academic achievements",
        "awards",
        "honors",
        "scholarships",
        "academic distinctions",
        "position of responsibility",
        "positions of responsibility",
        "extra curricular achievements",
        "extra curriculars",
        "extra curricular activities",
        "extracurricular achievements",
        "extracurriculars",
        "extracurricular activities"
    },
}

@dataclass
class ParsedSections:
    lines: dict[str, list[str]]

    def as_text(self) -> dict[str, str]:
        return {
            name: "\n".join(section_lines).strip()
            for name, section_lines in self.lines.items()
            if any(line.strip() for line in section_lines)
        }


class ResumeParser:
    """Heuristic-first parser with optional spaCy assistance."""

    def __init__(self) -> None:
        self.nlp, self.spacy_model = build_nlp()

    def parse_file(
        self,
        path: Path,
        text: str,
        extraction_warnings: list[str] | None = None,
    ) -> ResumeProfile:
        warnings = list(extraction_warnings or [])
        sections = split_sections(text)
        header_lines = sections.lines.get("header", [])

        profile = ResumeProfile(
            resume_id=path.stem,
            source_path=str(path),
            source_filename=path.name,
            parsed_at=datetime.now(timezone.utc).isoformat(),
            name=self.extract_name(text, header_lines),
            email=extract_primary_email(text),
            phone=extract_primary_phone(text),
            skills=extract_skills(sections.lines, text),
            education=extract_education(sections.lines),
            experience=extract_experience(sections.lines),
            certifications=extract_certifications(sections.lines, text),
            projects=extract_projects(sections.lines),
            sections=sections.as_text(),
            raw_text=text,
            metadata=ExtractionMetadata(
                file_type=path.suffix.lower().lstrip("."),
                source_sha256=sha256_file(path),
                text_length=len(text),
                warnings=warnings,
                spacy_model=self.spacy_model,
            ),
        )

        if not profile.name:
            profile.metadata.warnings.append("Name could not be extracted confidently.")
        if not profile.email:
            profile.metadata.warnings.append("Email address not found.")
        if not profile.skills:
            profile.metadata.warnings.append("No skills detected.")

        return profile

    def extract_name(self, text: str, header_lines: list[str]) -> str | None:
        header_text = "\n".join(header_lines[:12]).strip() or "\n".join(text.splitlines()[:12]).strip()
        candidates: list[tuple[int, str]] = []

        if "ner" in self.nlp.pipe_names:
            doc = self.nlp(header_text)
            for entity in doc.ents:
                candidate = clean_name_candidate(entity.text)
                if entity.label_ == "PERSON" and candidate:
                    candidates.append((120, candidate))

        first_lines = [line for line in header_text.splitlines() if line.strip()]
        for position, line in enumerate(first_lines[:8]):
            segments = [segment.strip() for segment in re.split(r"\s{2,}", line) if segment.strip()]
            for segment in segments or [line]:
                candidate = clean_name_candidate(segment)
                if not candidate:
                    continue
                score = score_name_candidate(candidate, position)
                if score:
                    candidates.append((score, candidate))

        if not candidates:
            return None

        best = max(candidates, key=lambda item: (item[0], -len(item[1])))
        return best[1]


def build_nlp() -> tuple[Language, str]:
    try:
        nlp = spacy.load("en_core_web_sm")
        return nlp, "en_core_web_sm"
    except OSError:
        nlp = spacy.blank("en")
        nlp.add_pipe("sentencizer")
        return nlp, "blank_en_sentencizer"


def split_sections(text: str) -> ParsedSections:
    sections: dict[str, list[str]] = defaultdict(list)
    current_section = "header"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            sections[current_section].append("")
            continue

        heading = detect_section_heading(line)
        if heading:
            current_section = heading
            sections.setdefault(current_section, [])
            continue

        sections[current_section].append(line)

    return ParsedSections(lines=dict(sections))


def detect_section_heading(line: str) -> str | None:
    normalized = normalize_heading(line)
    if not normalized or len(normalized) > 40:
        return None

    for section, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if normalized == alias:
                return section
            # Fix: Handle both "Selected Projects" and "Projects Architecture" safely
            if alias in normalized:
                # Ensure it's matching a whole word phrase boundary, not a partial fragment
                words = normalized.split()
                alias_words = alias.split()
                if all(w in words for w in alias_words):
                    return section

    return None


def normalize_heading(line: str) -> str:
    normalized = strip_bullet(line).lower()
    normalized = re.sub(r"[/:&,+()\-]", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def strip_bullet(line: str) -> str:
    return re.sub(rf"^[{re.escape(BULLET_CHARS)}\s]+", "", line).strip()


def clean_name_candidate(value: str) -> str | None:
    candidate = value.strip(" ,:-")
    if not candidate:
        return None
    if any(char.isdigit() for char in candidate):
        return None
    normalized = normalize_heading(candidate)
    if not normalized or normalized in BAD_NAME_TERMS:
        return None
    if any(term in normalized for term in BAD_NAME_TERMS):
        return None

    words = candidate.split()
    if len(words) < 2 or len(words) > 5:
        return None
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", word) for word in words):
        return None

    return " ".join(word.capitalize() if word.isupper() else word for word in words)


def score_name_candidate(candidate: str, position: int) -> int:
    score = 100 - position * 5
    words = candidate.split()
    if len(words) in {2, 3}:
        score += 10
    if candidate == candidate.upper() or candidate == candidate.title():
        score += 5
    if len(candidate) > 12:
        score += 3
    return score


def extract_primary_email(text: str) -> str | None:
    match = EMAIL_PATTERN.search(text)
    return match.group(0).lower() if match else None


def extract_primary_phone(text: str) -> str | None:
    for match in PHONE_PATTERN.finditer(text):
        candidate = match.group(0).strip()
        if "/" in candidate:
            continue
        digits = re.sub(r"\D", "", candidate)
        if len(digits) < 10 or len(digits) > 15:
            continue
        if candidate.startswith("+"):
            return f"+{digits}"
        return digits
    return None


def extract_skills(section_lines: dict[str, list[str]], text: str) -> list[str]:
    found: set[str] = set()
    skill_lines = list(section_lines.get("skills", []))

    for line in skill_lines:
        cleaned = strip_bullet(line)
        if not cleaned:
            continue
        payload = cleaned.split(":", 1)[1] if ":" in cleaned else cleaned
        for token in split_skill_candidates(payload):
            pretty = canonicalize_skill_token(token)
            if pretty:
                found.add(pretty)

    found.update(scan_skill_lexicon(text))

    return sorted(found, key=str.lower)


def split_skill_candidates(payload: str) -> list[str]:
    parts = re.split(r"[,/|]", payload)
    candidates: list[str] = []

    for part in parts:
        for token in re.split(r"\s+\band\b\s+", part, flags=re.IGNORECASE):
            cleaned = token.strip(" .;:-")
            if cleaned:
                candidates.append(cleaned)

    return candidates


def canonicalize_skill_token(token: str) -> str | None:
    normalized = token.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    if len(lowered) > 40:
        return None
    if lowered in {"programming languages", "software", "operating systems", "web designing languages"}:
        return None
    if lowered in SKILL_PATTERNS:
        return SKILL_PATTERNS[lowered]
    if not re.search(r"[A-Za-z]", normalized):
        return None

    acronym_map = {
        "nlp": "NLP",
        "sql": "SQL",
        "xml": "XML",
        "html": "HTML",
        "css": "CSS",
        "php": "PHP",
        "aws": "AWS",
        "api": "API",
    }
    return acronym_map.get(lowered, normalized.title())


def extract_education(section_lines: dict[str, list[str]]) -> list[EducationEntry]:
    lines = [strip_bullet(line) for line in section_lines.get("education", []) if strip_bullet(line)]
    rows = build_education_rows(lines)
    if not rows:
        return []

    results: list[EducationEntry] = []
    for row in rows:
        raw_text = " ".join(
            part for part in (row["year"], row["degree_text"], row["institution"], row["score"]) if part
        ).strip()
        results.append(
            EducationEntry(
                raw_text=raw_text,
                degree=extract_regex(DEGREE_PATTERN, row["degree_text"] or raw_text),
                institution=row["institution"] or extract_institution(raw_text),
                year=row["year"] or extract_regex(YEAR_PATTERN, raw_text),
                score=row["score"] or extract_regex(SCORE_PATTERN, raw_text),
            )
        )

    return results


def extract_experience(section_lines: dict[str, list[str]]) -> list[ExperienceEntry]:
    lines = [line for line in section_lines.get("experience", [])]
    if not lines:
        return []

    blocks = group_entries(lines, is_experience_block_start)
    results: list[ExperienceEntry] = []

    for block in blocks:
        cleaned_block = [strip_bullet(line) for line in block if strip_bullet(line)]
        if not cleaned_block:
            continue

        header = cleaned_block[0]
        segments = [segment.strip(" ,") for segment in re.split(r"\s{2,}", header) if segment.strip()]
        project_name = next(
            (
                clean_project_label(line.split(":", 1)[1].strip())
                for line in cleaned_block
                if line.lower().startswith("project name:")
            ),
            None,
        )
        title = project_name or (segments[0] if segments else collapse_internal_spacing(header))
        organization = segments[0] if project_name and segments else next(
            (
                segment
                for segment in segments[1:]
                if not DATE_RANGE_PATTERN.search(segment) and not PAREN_DATE_RANGE_PATTERN.search(segment)
            ),
            None,
        )
        date_range = (
            extract_regex(PAREN_DATE_RANGE_PATTERN, header)
            or extract_regex(DATE_RANGE_PATTERN, header)
            or extract_regex(YEAR_PATTERN, header)
        )
        description_lines = [
            collapse_internal_spacing(line)
            for line in cleaned_block[1:]
            if not normalize_heading(line).startswith(("project name", "area"))
        ]
        description = " ".join(description_lines).strip() or None

        results.append(
            ExperienceEntry(
                raw_text="\n".join(cleaned_block),
                title=title,
                organization=organization,
                date_range=date_range,
                description=description,
            )
        )

    return results


def extract_certifications(section_lines: dict[str, list[str]], text: str) -> list[str]:
    found: list[str] = []

    for line in section_lines.get("certifications", []):
        cleaned = strip_bullet(line)
        if cleaned:
            found.append(cleaned)

    if not found:
        for line in text.splitlines():
            lowered = line.lower()
            if "certif" in lowered and "degree/certificate" not in lowered:
                cleaned = strip_bullet(line)
                if cleaned and not detect_section_heading(cleaned):
                    found.append(cleaned)

    return deduplicate_preserving_order(found)


def extract_projects(section_lines: dict[str, list[str]]) -> list[ProjectEntry]:
    lines = [line for line in section_lines.get("projects", [])]
    if not lines:
        return []

    blocks = merge_project_blocks(group_entries(lines, is_project_block_start))
    results: list[ProjectEntry] = []

    for block in blocks:
        cleaned_block = [strip_bullet(line) for line in block if strip_bullet(line)]
        if not cleaned_block:
            continue

        name = extract_project_name(cleaned_block)
        description_parts = extract_project_description(cleaned_block)

        block_text = "\n".join(collapse_internal_spacing(line) for line in cleaned_block)
        technologies = sorted(scan_skill_lexicon(block_text), key=str.lower)
        results.append(
            ProjectEntry(
                raw_text=block_text,
                name=name,
                description=" ".join(description_parts).strip() or None,
                technologies=technologies,
            )
        )

    return results


def extract_project_name(lines: list[str]) -> str | None:
    for index, line in enumerate(lines):
        if normalize_heading(line) == "topic" and index + 1 < len(lines):
            collected: list[str] = []
            for candidate in lines[index + 1 :]:
                heading = normalize_heading(candidate)
                if heading == "work done":
                    break
                if candidate:
                    collected.append(candidate)
            if collected:
                return " ".join(collected).strip()
    for line in lines:
        match = re.search(r"project name\s*:?\s*(.+)", line, flags=re.IGNORECASE)
        if match:
            return clean_project_label(match.group(1).strip(" -"))
        match = re.search(r"topic\s*:?\s*(.+)", line, flags=re.IGNORECASE)
        if match:
            return clean_project_label(match.group(1).strip(" -"))

    first = lines[0]
    segments = [segment.strip() for segment in re.split(r"\s{2,}", first) if segment.strip()]
    candidate = segments[0] if segments else first
    candidate = PAREN_DATE_RANGE_PATTERN.sub("", candidate)
    candidate = DATE_RANGE_PATTERN.sub("", candidate).strip(" ,-")
    return candidate or None


def is_experience_block_start(line: str) -> bool:
    cleaned = strip_bullet(line)
    if not cleaned or len(cleaned.split()) < 3:
        return False
    return bool(DATE_RANGE_PATTERN.search(cleaned) or PAREN_DATE_RANGE_PATTERN.search(cleaned))


def is_project_block_start(line: str) -> bool:
    cleaned = strip_bullet(line)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered.startswith(("guide:", "organisation:", "organization:")):
        return True
    if DATE_RANGE_PATTERN.search(cleaned):
        return True
    return False


def group_entries(lines: list[str], start_predicate) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if not line.strip():
            if current:
                blocks.append(current)
                current = []
            continue

        if current and start_predicate(line):
            blocks.append(current)
            current = [line]
            continue

        current.append(line)

    if current:
        blocks.append(current)

    return blocks


def extract_regex(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1) if match.lastindex else match.group(0)


def collapse_internal_spacing(text: str) -> str:
    return re.sub(r"\s{2,}", " ", text).strip()


def looks_like_education_entry(line: str) -> bool:
    return bool(
        DEGREE_PATTERN.search(line)
        or YEAR_PATTERN.search(line)
        or SCORE_PATTERN.search(line)
        or INSTITUTION_PATTERN.search(line)
    )


def scan_skill_lexicon(text: str) -> set[str]:
    return {skill for skill, pattern in SKILL_REGEXES.items() if pattern.search(text)}


def build_education_rows(lines: list[str]) -> list[dict[str, str | None]]:
    if sum(len(split_columns(line)) >= 3 for line in lines) >= 2:
        return build_education_rows_from_columns(lines)
    return build_education_rows_from_lines(lines)


def build_education_rows_from_columns(lines: list[str]) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None

    for raw_line in lines:
        segments = split_columns(raw_line)
        joined = " ".join(segments)
        if not joined or is_education_header_line(joined):
            continue

        starts_new_row = is_education_row_start(segments[0])
        if len(segments) == 1 and current is not None and not YEAR_PATTERN.search(segments[0]):
            starts_new_row = False

        if current is None or starts_new_row:
            if current and any(current.values()):
                rows.append(normalize_education_row(current))
            current = initialize_education_row(segments)
            continue

        append_education_continuation(current, segments)

    if current and any(current.values()):
        rows.append(normalize_education_row(current))

    return rows


def build_education_rows_from_lines(lines: list[str]) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None

    for raw_line in lines:
        line = collapse_internal_spacing(raw_line)
        if not line or is_education_header_line(line):
            continue
        if current and not is_education_row_start(line):
            current["degree_text"] = join_text(current["degree_text"], line)
            continue
        if looks_like_education_entry(line):
            if current and any(current.values()):
                rows.append(normalize_education_row(current))
            current = {
                "year": extract_regex(YEAR_PATTERN, line),
                "degree_text": line,
                "institution": extract_institution(line),
                "score": extract_regex(SCORE_PATTERN, line),
            }

    if current and any(current.values()):
        rows.append(normalize_education_row(current))

    return rows


def split_columns(line: str) -> list[str]:
    return [collapse_internal_spacing(segment) for segment in re.split(r"\s{2,}", line) if segment.strip()]


def initialize_education_row(segments: list[str]) -> dict[str, str | None]:
    if not segments:
        return {"year": None, "degree_text": None, "institution": None, "score": None}

    year_index = next((index for index, segment in enumerate(segments) if YEAR_PATTERN.search(segment)), None)
    score_index = next((index for index, segment in enumerate(segments) if SCORE_PATTERN.search(segment)), None)

    year = segments[year_index] if year_index is not None else None

    if year_index == 0:
        degree_text = segments[1] if len(segments) > 1 else None
        institution = segments[2] if len(segments) > 2 else None
        score = segments[3] if len(segments) > 3 else None
    elif year_index == 1:
        degree_text = segments[0]
        institution = segments[2] if len(segments) > 2 else None
        score = segments[3] if len(segments) > 3 else None
    elif year_index is not None:
        degree_text = " ".join(segments[:year_index]) or None
        if score_index is not None:
            institution = " ".join(segments[year_index + 1 : score_index]) or None
            score = " ".join(segments[score_index:]) or None
        else:
            institution = " ".join(segments[year_index + 1 :]) or None
            score = None
    else:
        degree_text = segments[0] if segments else None
        institution = segments[1] if len(segments) > 1 else None
        score = segments[2] if len(segments) > 2 else None

    return {
        "year": year,
        "degree_text": degree_text,
        "institution": institution,
        "score": score,
    }


def append_education_continuation(row: dict[str, str | None], segments: list[str]) -> None:
    if not segments:
        return

    if len(segments) == 1:
        segment = segments[0]
        if SCORE_PATTERN.search(segment):
            row["score"] = join_text(row.get("score"), segment)
            return
        if YEAR_PATTERN.search(segment):
            row["year"] = join_text(row.get("year"), segment)
            return
        if DEGREE_PATTERN.search(segment) and not DEGREE_PATTERN.search(row.get("degree_text") or ""):
            row["degree_text"] = join_text(row.get("degree_text"), segment)
        else:
            row["institution"] = join_text(row.get("institution"), segment)
        return

    if len(segments) >= 2:
        row["degree_text"] = join_text(row.get("degree_text"), segments[0])
        row["institution"] = join_text(row.get("institution"), segments[1])
    if len(segments) >= 3:
        row["score"] = join_text(row.get("score"), segments[2])


def normalize_education_row(row: dict[str, str | None]) -> dict[str, str | None]:
    return {
        "year": collapse_internal_spacing(row.get("year") or "") or None,
        "degree_text": collapse_internal_spacing(row.get("degree_text") or "") or None,
        "institution": collapse_internal_spacing(row.get("institution") or "") or None,
        "score": collapse_internal_spacing(row.get("score") or "") or None,
    }


def join_text(current: str | None, extra: str | None) -> str | None:
    if not extra:
        return current
    if not current:
        return extra
    return f"{current} {extra}".strip()


def is_education_header_line(line: str) -> bool:
    normalized = normalize_heading(line)
    exact_headers = {
        "year",
        "degree certificate",
        "degree board",
        "institute school",
        "board university",
        "marks obtained",
        "completion",
        "cgpa",
        "examination",
    }
    if normalized in exact_headers:
        return True

    header_keywords = ("year", "college", "school", "board", "cgpa", "degree", "marks", "completion")
    return sum(keyword in normalized for keyword in header_keywords) >= 3


def is_education_row_start(line: str) -> bool:
    return bool(
        re.match(
            r"^(?:"
            r"(?:19|20)\d{2}(?:\s*[-/]\s*(?:present|current|(?:19|20)\d{2}))?"
            r"|dual degree"
            r"|class\s+[xiv]+"
            r"|b\.?\s*tech"
            r"|m\.?\s*tech"
            r"|bachelor"
            r"|master"
            r"|senior secondary"
            r"|secondary"
            r"|cbse"
            r")",
            line,
            re.IGNORECASE,
        )
    )


def extract_institution(text: str) -> str | None:
    match = INSTITUTION_PATTERN.search(text)
    if not match:
        return None
    return collapse_internal_spacing(match.group(1)).strip(" ,")


def extract_project_description(lines: list[str]) -> list[str]:
    descriptions: list[str] = []
    collecting_work_done = False

    for line in lines:
        heading = normalize_heading(line)
        lowered = line.lower()

        if heading == "work done":
            collecting_work_done = True
            continue
        if lowered.startswith("work done"):
            collecting_work_done = True
            payload = re.sub(r"(?i)^work done\s*:?\s*", "", line).strip(" :-")
            if payload:
                descriptions.append(collapse_internal_spacing(payload))
            continue
        if heading == "topic":
            continue
        if lowered.startswith("project name:"):
            continue
        if lowered.startswith(("guide:", "organisation:", "organization:")):
            continue
        if lowered.startswith("area:"):
            descriptions.append(collapse_internal_spacing(line.split(":", 1)[1].strip()))
            continue
        if collecting_work_done:
            descriptions.append(collapse_internal_spacing(line))
            continue

    if descriptions:
        return descriptions

    for line in lines[1:]:
        lowered = line.lower()
        if lowered.startswith(("guide:", "organisation:", "organization:", "project name:")):
            continue
        descriptions.append(collapse_internal_spacing(line))

    return descriptions


def clean_project_label(value: str) -> str:
    label = value.split("Area:", 1)[0]
    return collapse_internal_spacing(label).strip(" ,-")


def merge_project_blocks(blocks: list[list[str]]) -> list[list[str]]:
    merged: list[list[str]] = []
    index = 0

    while index < len(blocks):
        block = blocks[index]
        if (
            len(block) == 1
            and index + 1 < len(blocks)
            and strip_bullet(block[0]).lower().startswith(("guide:", "organisation:", "organization:"))
        ):
            merged.append(block + blocks[index + 1])
            index += 2
            continue
        merged.append(block)
        index += 1

    return merged


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deduplicate_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result
