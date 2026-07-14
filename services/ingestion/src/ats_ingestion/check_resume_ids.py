from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
import re

from ats_ingestion.storage import sanitize_resume_id


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REPORT_PATH = REPO_ROOT / "data" / "processed" / "resume_id_audit.md"
AUDITABLE_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}

GENERIC_TOKENS = {
    "bio",
    "biodata",
    "candidate",
    "copy",
    "curriculum",
    "cv",
    "data",
    "draft",
    "example",
    "final",
    "latest",
    "new",
    "profile",
    "resume",
    "resumes",
    "rev",
    "revised",
    "revision",
    "update",
    "updated",
    "ver",
    "version",
    "vitae",
}
TEMPLATE_TOKENS = {"example", "sample", "template"}
MONTH_TOKENS = {
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
}
MARKER_PATTERNS = (
    re.compile(r"\(\s*\d+\s*\)"),
    re.compile(r"\[\s*\d+\s*\]"),
    re.compile(r"\bcopy\b", re.IGNORECASE),
    re.compile(r"\bfinal\b", re.IGNORECASE),
    re.compile(r"\bupdated?\b", re.IGNORECASE),
    re.compile(r"\bnew\b", re.IGNORECASE),
    re.compile(r"\blatest\b", re.IGNORECASE),
    re.compile(r"\bdraft\b", re.IGNORECASE),
    re.compile(r"\brevised?\b", re.IGNORECASE),
    re.compile(r"\brev(?:ision)?\b", re.IGNORECASE),
    re.compile(r"\bv(?:er(?:sion)?)?\s*[_-]?\s*\d+\b", re.IGNORECASE),
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
TIMESTAMP_PATTERN = re.compile(r"^\d{10,17}$")
YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")


@dataclass(frozen=True)
class FileRecord:
    index: int
    path: Path
    relative_path: str
    stem: str
    suffix: str
    suffix_lower: str
    size_bytes: int
    modified_at: str
    sanitized_id: str
    stem_lower: str
    stem_compact: str
    marker_base: str
    marker_base_compact: str
    candidate_key: str
    candidate_compact: str
    informative_tokens: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    total_files: int
    unique_stems: int
    unique_sanitized_ids: int
    exact_stem_collisions: dict[str, list[FileRecord]]
    sanitized_id_collisions: dict[str, list[FileRecord]]
    extension_only_duplicates: dict[str, list[FileRecord]]
    case_only_duplicates: dict[str, list[FileRecord]]
    marker_groups: dict[str, list[FileRecord]]
    manual_review_groups: list[dict]


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            self.parent[root_left] = root_right
            return
        if self.rank[root_left] > self.rank[root_right]:
            self.parent[root_right] = root_left
            return
        self.parent[root_right] = root_left
        self.rank[root_left] += 1


def discover_resume_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDITABLE_EXTENSIONS
    )


def split_tokens(value: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(value)]


def strip_marker_patterns(value: str) -> str:
    normalized = value
    for pattern in MARKER_PATTERNS:
        normalized = pattern.sub(" ", normalized)
    return collapse_whitespace(normalized)


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def compact_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def is_date_or_counter_token(token: str) -> bool:
    if token in MONTH_TOKENS:
        return True
    if TIMESTAMP_PATTERN.fullmatch(token):
        return True
    if YEAR_PATTERN.fullmatch(token):
        return True
    if token.isdigit():
        return True
    return False


def build_marker_base(stem: str) -> tuple[str, str]:
    normalized = strip_marker_patterns(stem.replace("_", " ").replace("-", " "))
    tokens = split_tokens(normalized)
    if not tokens:
        return "", ""
    base = " ".join(tokens)
    return base, "".join(tokens)


def build_candidate_key(stem: str) -> tuple[str, str, tuple[str, ...]]:
    normalized = strip_marker_patterns(stem.replace("_", " ").replace("-", " "))
    tokens = []
    for token in split_tokens(normalized):
        if token in GENERIC_TOKENS:
            continue
        if is_date_or_counter_token(token):
            continue
        tokens.append(token)
    candidate_key = " ".join(tokens)
    return candidate_key, "".join(tokens), tuple(tokens)


def is_template_like(record: FileRecord) -> bool:
    return bool(set(split_tokens(record.stem)) & TEMPLATE_TOKENS)


def build_file_records(input_dir: Path, files: list[Path]) -> list[FileRecord]:
    records: list[FileRecord] = []
    for index, path in enumerate(files):
        stat = path.stat()
        marker_base, marker_base_compact = build_marker_base(path.stem)
        candidate_key, candidate_compact, informative_tokens = build_candidate_key(path.stem)
        records.append(
            FileRecord(
                index=index,
                path=path,
                relative_path=str(path.relative_to(input_dir)),
                stem=path.stem,
                suffix=path.suffix,
                suffix_lower=path.suffix.lower(),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                sanitized_id=sanitize_resume_id(path.stem),
                stem_lower=path.stem.lower(),
                stem_compact=compact_text(path.stem),
                marker_base=marker_base,
                marker_base_compact=marker_base_compact,
                candidate_key=candidate_key,
                candidate_compact=candidate_compact,
                informative_tokens=informative_tokens,
            )
        )
    return records


def build_group_map(records: list[FileRecord], key_fn) -> dict[str, list[FileRecord]]:
    grouped: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        key = key_fn(record)
        grouped[key].append(record)
    return grouped


def keep_multi_record_groups(groups: dict[str, list[FileRecord]]) -> dict[str, list[FileRecord]]:
    return {
        key: sorted(value, key=lambda record: record.relative_path.lower())
        for key, value in groups.items()
        if len(value) > 1
    }


def detect_extension_only_duplicates(records: list[FileRecord]) -> dict[str, list[FileRecord]]:
    grouped = keep_multi_record_groups(build_group_map(records, lambda record: record.stem))
    return {
        stem: value
        for stem, value in grouped.items()
        if len({record.suffix_lower for record in value}) > 1
    }


def detect_case_only_duplicates(records: list[FileRecord]) -> dict[str, list[FileRecord]]:
    grouped = keep_multi_record_groups(build_group_map(records, lambda record: record.stem_lower))
    return {
        lower_stem: value
        for lower_stem, value in grouped.items()
        if len({record.stem for record in value}) > 1
    }


def detect_marker_groups(records: list[FileRecord]) -> dict[str, list[FileRecord]]:
    grouped = keep_multi_record_groups(build_group_map(records, lambda record: record.marker_base_compact))
    marker_groups: dict[str, list[FileRecord]] = {}
    for compact_key, value in grouped.items():
        if not compact_key:
            continue
        if len({record.stem_lower for record in value}) <= 1:
            continue
        if not any(record.marker_base_compact != record.stem_compact for record in value):
            continue
        marker_groups[compact_key] = value
    return marker_groups


def pair_key(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


def add_group_reason(
    uf: UnionFind,
    reasons: dict[tuple[int, int], set[str]],
    grouped_records: list[FileRecord],
    reason: str,
) -> None:
    for left, right in combinations(grouped_records, 2):
        uf.union(left.index, right.index)
        reasons.setdefault(pair_key(left.index, right.index), set()).add(reason)


def is_informative_candidate(record: FileRecord) -> bool:
    token_count = len(record.informative_tokens)
    if token_count >= 2:
        return True
    if token_count == 1 and len(record.candidate_compact) >= 7:
        return True
    return False


def share_strong_token_overlap(left: FileRecord, right: FileRecord) -> bool:
    left_tokens = set(left.informative_tokens)
    right_tokens = set(right.informative_tokens)
    if not left_tokens or not right_tokens:
        return False
    overlap = left_tokens & right_tokens
    if not overlap:
        return False
    overlap_ratio = len(overlap) / min(len(left_tokens), len(right_tokens))
    return overlap_ratio >= 0.75


def file_size_similarity(left: FileRecord, right: FileRecord) -> float:
    if left.size_bytes == 0 or right.size_bytes == 0:
        return 0.0
    return min(left.size_bytes, right.size_bytes) / max(left.size_bytes, right.size_bytes)


def build_manual_review_groups(
    records: list[FileRecord],
    sanitized_id_collisions: dict[str, list[FileRecord]],
    extension_only_duplicates: dict[str, list[FileRecord]],
    case_only_duplicates: dict[str, list[FileRecord]],
    marker_groups: dict[str, list[FileRecord]],
) -> list[dict]:
    uf = UnionFind(len(records))
    reasons: dict[tuple[int, int], set[str]] = {}

    for sanitized_id, grouped_records in sanitized_id_collisions.items():
        add_group_reason(uf, reasons, grouped_records, f"same sanitized resume_id `{sanitized_id}`")
    for stem, grouped_records in extension_only_duplicates.items():
        add_group_reason(uf, reasons, grouped_records, f"same stem `{stem}` with different extensions")
    for lower_stem, grouped_records in case_only_duplicates.items():
        add_group_reason(uf, reasons, grouped_records, f"same stem ignoring case `{lower_stem}`")
    for marker_key, grouped_records in marker_groups.items():
        if any(is_template_like(record) for record in grouped_records):
            continue
        if not any(is_informative_candidate(record) for record in grouped_records):
            continue
        add_group_reason(
            uf,
            reasons,
            grouped_records,
            f"same marker-stripped base `{marker_key}`",
        )

    candidate_groups = keep_multi_record_groups(build_group_map(records, lambda record: record.candidate_compact))
    for candidate_key, grouped_records in candidate_groups.items():
        if not candidate_key:
            continue
        if any(is_template_like(record) for record in grouped_records):
            continue
        if not all(is_informative_candidate(record) for record in grouped_records):
            continue
        add_group_reason(
            uf,
            reasons,
            grouped_records,
            f"same normalized candidate key `{candidate_key}`",
        )

    informative_records = [
        record
        for record in records
        if is_informative_candidate(record) and not is_template_like(record)
    ]
    for left, right in combinations(informative_records, 2):
        if left.candidate_compact == right.candidate_compact:
            continue
        if not left.candidate_compact or not right.candidate_compact:
            continue
        if left.candidate_compact[0] != right.candidate_compact[0]:
            continue
        if abs(len(left.candidate_compact) - len(right.candidate_compact)) > 4:
            continue

        similarity = SequenceMatcher(None, left.candidate_compact, right.candidate_compact).ratio()
        size_similarity = file_size_similarity(left, right)
        has_overlap = share_strong_token_overlap(left, right)
        compact_contains = (
            left.candidate_compact in right.candidate_compact
            or right.candidate_compact in left.candidate_compact
        )

        near_match = similarity >= 0.92 and (has_overlap or compact_contains or size_similarity >= 0.7)
        token_match = has_overlap and (similarity >= 0.84 or size_similarity >= 0.85 or compact_contains)
        if not near_match and not token_match:
            continue

        reason_parts = [f"similar normalized name (`{left.candidate_key}` vs `{right.candidate_key}`)"]
        reason_parts.append(f"similarity={similarity:.2f}")
        if has_overlap:
            reason_parts.append("strong token overlap")
        if size_similarity >= 0.7:
            reason_parts.append(f"size_ratio={size_similarity:.2f}")
        if compact_contains:
            reason_parts.append("one normalized key contains the other")

        uf.union(left.index, right.index)
        reasons.setdefault(pair_key(left.index, right.index), set()).add(", ".join(reason_parts))

    component_members: dict[int, list[FileRecord]] = defaultdict(list)
    for record in records:
        component_members[uf.find(record.index)].append(record)

    manual_review_groups: list[dict] = []
    for grouped_records in component_members.values():
        if len(grouped_records) <= 1:
            continue
        component_pairs = []
        component_reasons: set[str] = set()
        for left, right in combinations(sorted(grouped_records, key=lambda item: item.index), 2):
            reason_set = reasons.get(pair_key(left.index, right.index))
            if not reason_set:
                continue
            ordered_reasons = sorted(reason_set)
            component_reasons.update(ordered_reasons)
            component_pairs.append(
                {
                    "left": left.relative_path,
                    "right": right.relative_path,
                    "reasons": ordered_reasons,
                }
            )
        if not component_pairs:
            continue
        manual_review_groups.append(
            {
                "files": sorted(grouped_records, key=lambda record: record.relative_path.lower()),
                "reasons": sorted(component_reasons),
                "pair_reasons": component_pairs,
            }
        )

    manual_review_groups.sort(
        key=lambda group: (-len(group["files"]), group["files"][0].relative_path.lower())
    )
    return manual_review_groups


def run_audit(input_dir: Path) -> AuditResult:
    files = discover_resume_files(input_dir)
    if not files:
        raise RuntimeError(f"No auditable resume files found in {input_dir}")

    records = build_file_records(input_dir, files)
    exact_stem_collisions = keep_multi_record_groups(build_group_map(records, lambda record: record.stem))
    sanitized_id_collisions = keep_multi_record_groups(build_group_map(records, lambda record: record.sanitized_id))
    extension_only_duplicates = detect_extension_only_duplicates(records)
    case_only_duplicates = detect_case_only_duplicates(records)
    marker_groups = detect_marker_groups(records)
    manual_review_groups = build_manual_review_groups(
        records=records,
        sanitized_id_collisions=sanitized_id_collisions,
        extension_only_duplicates=extension_only_duplicates,
        case_only_duplicates=case_only_duplicates,
        marker_groups=marker_groups,
    )

    return AuditResult(
        total_files=len(records),
        unique_stems=len({record.stem for record in records}),
        unique_sanitized_ids=len({record.sanitized_id for record in records}),
        exact_stem_collisions=exact_stem_collisions,
        sanitized_id_collisions=sanitized_id_collisions,
        extension_only_duplicates=extension_only_duplicates,
        case_only_duplicates=case_only_duplicates,
        marker_groups=marker_groups,
        manual_review_groups=manual_review_groups,
    )


def format_file_record(record: FileRecord) -> str:
    return (
        f"`{record.relative_path}` "
        f"(stem=`{record.stem}`, sanitized_id=`{record.sanitized_id}`, "
        f"ext=`{record.suffix_lower}`, size={record.size_bytes}B, modified={record.modified_at})"
    )


def format_group_section(
    title: str,
    groups: dict[str, list[FileRecord]],
    empty_message: str,
) -> list[str]:
    lines = [title]
    if not groups:
        lines.append(empty_message)
        lines.append("")
        return lines

    for key in sorted(groups):
        lines.append(f"- `{key}`")
        for record in groups[key]:
            lines.append(f"  - {format_file_record(record)}")
    lines.append("")
    return lines


def render_report(input_dir: Path, result: AuditResult) -> str:
    lines = [
        "# Collision Report",
        f"Total files scanned: {result.total_files}",
        f"Unique filename stems: {result.unique_stems}",
        f"Unique sanitized IDs: {result.unique_sanitized_ids}",
        "",
        "Heuristic note: the `Potential duplicate resumes requiring manual review` section is intentionally over-inclusive.",
        "Grouping there is based on filename-only signals after stripping generic resume words, copy/version markers, and date/counter suffixes.",
        "File size and modified timestamps are included as supporting context only, not as proof of identity.",
        "Every flagged group still requires human review before any file is renamed, removed, deduplicated, or persisted.",
        "",
    ]
    lines.extend(
        format_group_section(
            "## Exact stem collisions:",
            result.exact_stem_collisions,
            "None.",
        )
    )
    lines.extend(
        format_group_section(
            "## Sanitized ID collisions:",
            result.sanitized_id_collisions,
            "None.",
        )
    )

    lines.append("## Suspicious filename variants:")
    lines.append(f"- extension-only duplicates: {len(result.extension_only_duplicates)} group(s)")
    lines.append(f"- case-only duplicates: {len(result.case_only_duplicates)} group(s)")
    lines.append(f"- copy/version-marker groups: {len(result.marker_groups)} group(s)")
    lines.append("")

    lines.extend(
        format_group_section(
            "### extension-only duplicates:",
            result.extension_only_duplicates,
            "None.",
        )
    )
    lines.extend(
        format_group_section(
            "### case-only duplicates:",
            result.case_only_duplicates,
            "None.",
        )
    )
    lines.extend(
        format_group_section(
            "### copy/version-marker groups:",
            result.marker_groups,
            "None.",
        )
    )

    lines.append("## Potential duplicate resumes requiring manual review:")
    if not result.manual_review_groups:
        lines.append("None.")
        lines.append("")
        return "\n".join(lines).strip() + "\n"

    for index, group in enumerate(result.manual_review_groups, start=1):
        lines.append(f"- Group {index}: {len(group['files'])} file(s)")
        lines.append("  Why grouped:")
        for reason in group["reasons"]:
            lines.append(f"  - {reason}")
        lines.append("  Files:")
        for record in group["files"]:
            lines.append(f"  - {format_file_record(record)}")
        lines.append("  Pair evidence:")
        for pair in group["pair_reasons"]:
            reason_text = "; ".join(pair["reasons"])
            lines.append(f"  - `{pair['left']}` <-> `{pair['right']}`: {reason_text}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_report(report_path: Path, content: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit resume filenames for exact collisions and likely duplicate variants."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    input_dir = args.input_dir.resolve()
    report_path = args.report_path.resolve()

    try:
        result = run_audit(input_dir)
    except RuntimeError as exc:
        print(exc)
        return 1

    report = render_report(input_dir, result)
    write_report(report_path, report)

    print("Collision Report")
    print(f"Total files scanned: {result.total_files}")
    print(f"Unique filename stems: {result.unique_stems}")
    print(f"Unique sanitized IDs: {result.unique_sanitized_ids}")
    print(f"Exact stem collisions: {len(result.exact_stem_collisions)} group(s)")
    print(f"Sanitized ID collisions: {len(result.sanitized_id_collisions)} group(s)")
    print(f"extension-only duplicates: {len(result.extension_only_duplicates)} group(s)")
    print(f"case-only duplicates: {len(result.case_only_duplicates)} group(s)")
    print(f"copy/version-marker groups: {len(result.marker_groups)} group(s)")
    print(f"Potential duplicate manual-review groups: {len(result.manual_review_groups)}")
    print(f"Report written to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
