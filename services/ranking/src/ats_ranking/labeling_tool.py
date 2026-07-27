from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ats_ranking.cli import DEFAULT_ENV_FILE
from ats_ranking.config import load_postgres_settings
from ats_ranking.labels import build_label_lookup
from ats_ranking.labels import default_split_for_job
from ats_ranking.labels import load_relevance_labels
from ats_ranking.labels import normalize_split
from ats_ranking.repository import RankingRepository
from ats_ranking.signals import compute_ranking_signals


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_LABELS_PATH = REPO_ROOT / "data" / "labels" / "resume_jd_relevance.jsonl"
DEFAULT_EXCLUDED_PATH = REPO_ROOT / "data" / "labels" / "resume_jd_relevance_excluded.jsonl"

SKIP_REASONS = {
    "1": "not-a-resume",
    "2": "template-junk",
    "3": "parser-extraction-failure-suspected",
    "4": "other",
}


@dataclass(frozen=True)
class SampledPair:
    job: dict[str, Any]
    candidate: dict[str, Any]
    sample_source: str
    heuristic_score: float
    retrieval_rank: int | None
    ranking_rank: int | None
    semantic_similarity: float


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive manual labeling tool for job-resume relevance."
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--labels-path", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--excluded-path", type=Path, default=DEFAULT_EXCLUDED_PATH)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--outside-sample-size", type=int, default=15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source", default="manual_review")
    parser.add_argument("--job-id", action="append", default=[])
    parser.add_argument("--max-pairs", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    labels_path = args.labels_path.resolve()
    excluded_path = args.excluded_path.resolve()
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    excluded_path.parent.mkdir(parents=True, exist_ok=True)

    existing_labels = load_relevance_labels(labels_path) if labels_path.exists() else []
    reviewed_keys = set(build_label_lookup(existing_labels))
    reviewed_keys.update(load_excluded_keys(excluded_path))

    repository = RankingRepository(load_postgres_settings(args.env_file))
    with repository.connect() as connection:
        repository.ensure_schema(connection)
        jobs = repository.fetch_jobs(connection)
        if args.job_id:
            allowed = set(args.job_id)
            jobs = [job for job in jobs if job["job_id"] in allowed]
        if not jobs:
            print("No matching jobs found in PostgreSQL.")
            return 1

        all_candidates = repository.fetch_all_candidate_profiles(connection)
        candidate_by_id = {row["resume_id"]: row for row in all_candidates}
        job_embeddings = repository.fetch_job_embeddings(connection)
        candidate_embeddings = repository.fetch_candidate_embeddings(connection)

        pairs = build_labeling_queue(
            jobs=jobs,
            repository=repository,
            connection=connection,
            candidate_by_id=candidate_by_id,
            job_embeddings=job_embeddings,
            candidate_embeddings=candidate_embeddings,
            reviewed_keys=reviewed_keys,
            top_k=args.top_k,
            outside_sample_size=args.outside_sample_size,
            seed=args.seed,
        )

    if args.max_pairs is not None:
        pairs = pairs[: args.max_pairs]

    if not pairs:
        print("No unlabeled job-resume pairs remain for the requested sampling settings.")
        return 0

    print(
        f"Loaded {len(pairs)} unlabeled pair(s). "
        "Judge relevance independently; do not rubber-stamp the current heuristic score."
    )

    for index, pair in enumerate(pairs, start=1):
        render_pair(index, len(pairs), pair)
        action = prompt_action()
        if action == "quit":
            print("Stopping labeling session.")
            return 0
        if action == "skip":
            record = build_excluded_record(pair=pair, source=args.source)
            append_jsonl(excluded_path, record)
            continue

        record = build_label_record(pair=pair, source=args.source, label_value=action)
        append_jsonl(labels_path, record)

    print("Completed labeling queue.")
    return 0


def build_labeling_queue(
    jobs: list[dict[str, Any]],
    repository: RankingRepository,
    connection,
    candidate_by_id: dict[str, dict[str, Any]],
    job_embeddings: dict[str, list[float]],
    candidate_embeddings: dict[str, list[float]],
    reviewed_keys: set[tuple[str, str]],
    top_k: int,
    outside_sample_size: int,
    seed: int,
) -> list[SampledPair]:
    pairs: list[SampledPair] = []
    for job in jobs:
        ranked_rows = repository.fetch_ranked_candidates(connection, job["job_id"])
        top_rows = ranked_rows[:top_k]
        top_resume_ids = {row["resume_id"] for row in top_rows}

        for row in top_rows:
            key = (job["job_id"], row["resume_id"])
            if key in reviewed_keys:
                continue
            pairs.append(
                SampledPair(
                    job=job,
                    candidate=row,
                    sample_source="top-k-retrieval",
                    heuristic_score=float(row["final_score"]),
                    retrieval_rank=row["retrieval_rank"],
                    ranking_rank=row["ranking_rank"],
                    semantic_similarity=float(row["semantic_similarity"]),
                )
            )

        remaining_candidates = [
            candidate
            for resume_id, candidate in candidate_by_id.items()
            if resume_id not in top_resume_ids
        ]
        rng = random.Random(f"{seed}:{job['job_id']}")
        outside_rows = rng.sample(remaining_candidates, min(outside_sample_size, len(remaining_candidates)))
        job_embedding = job_embeddings.get(job["job_id"])
        for candidate in outside_rows:
            key = (job["job_id"], candidate["resume_id"])
            if key in reviewed_keys:
                continue
            semantic_similarity = compute_semantic_similarity(job_embedding, candidate_embeddings.get(candidate["resume_id"]))
            candidate_row = dict(candidate)
            candidate_row["semantic_similarity"] = semantic_similarity
            signals = compute_ranking_signals(job, candidate_row)
            pairs.append(
                SampledPair(
                    job=job,
                    candidate=candidate_row,
                    sample_source="outside-top-k-random",
                    heuristic_score=signals.heuristic_score,
                    retrieval_rank=None,
                    ranking_rank=None,
                    semantic_similarity=signals.semantic_similarity,
                )
            )

    return pairs


def compute_semantic_similarity(
    job_embedding: list[float] | None,
    candidate_embedding: list[float] | None,
) -> float:
    if not job_embedding or not candidate_embedding:
        return 0.0
    dot = sum(float(left) * float(right) for left, right in zip(job_embedding, candidate_embedding))
    return float((dot + 1.0) / 2.0)


def render_pair(index: int, total: int, pair: SampledPair) -> None:
    candidate = pair.candidate
    profile = candidate["profile_json"]
    print("\n" + "=" * 100)
    print(f"[{index}/{total}] job_id={pair.job['job_id']} resume_id={candidate['resume_id']}")
    print(f"Sample source: {pair.sample_source}")
    print(f"Job title: {pair.job['job_title']}")
    print(f"Required skills: {format_list(pair.job.get('required_skills') or [])}")
    print(f"Preferred skills: {format_list(pair.job.get('preferred_skills') or [])}")
    print(f"Candidate name: {candidate.get('name') or '(missing)'}")
    print(f"Candidate email: {candidate.get('email') or '(missing)'}")
    print(f"Candidate skills: {format_list(candidate.get('skills') or [])}")
    warnings = profile.get("metadata", {}).get("warnings", [])
    if warnings:
        print(f"Parser warnings: {format_list(warnings)}")
    print(
        "Current ranking context: "
        f"heuristic_score={pair.heuristic_score:.6f}, "
        f"semantic_similarity={pair.semantic_similarity:.6f}, "
        f"retrieval_rank={pair.retrieval_rank if pair.retrieval_rank is not None else 'outside-top-25'}, "
        f"ranking_rank={pair.ranking_rank if pair.ranking_rank is not None else 'not-ranked'}"
    )
    print("Judge relevance independently; use notes if the parser display looks wrong.")
    print("--- experience/project snippets ---")
    snippets = extract_candidate_snippets(profile)
    if snippets:
        for label, snippet in snippets:
            print(f"{label}: {snippet}")
    else:
        print("(no experience/project snippets available)")


def extract_candidate_snippets(profile: dict[str, Any]) -> list[tuple[str, str]]:
    snippets: list[tuple[str, str]] = []
    for collection_name, label in (("experience", "Experience"), ("projects", "Project")):
        for entry in profile.get(collection_name, [])[:2]:
            raw_text = str(entry.get("raw_text") or "").strip()
            if raw_text:
                snippets.append((label, truncate_text(raw_text, 260)))
        if len(snippets) >= 2:
            break
    return snippets[:2]


def prompt_action() -> int | str:
    while True:
        raw = input("Label [0-3], skip [s], quit [q]: ").strip().lower()
        if raw in {"q", "quit"}:
            return "quit"
        if raw in {"s", "skip"}:
            return "skip"
        if raw in {"0", "1", "2", "3"}:
            return int(raw)
        print("Enter 0, 1, 2, 3, s, or q.")


def build_label_record(pair: SampledPair, source: str, label_value: int) -> dict[str, Any]:
    default_split = default_split_for_job(pair.job["job_id"])
    split = prompt_split_override(default_split)
    notes = clean_optional_input("Notes (optional): ")
    return {
        "job_id": pair.job["job_id"],
        "resume_id": pair.candidate["resume_id"],
        "label": label_value,
        "split": split,
        "source": source,
        "notes": notes,
    }


def build_excluded_record(pair: SampledPair, source: str) -> dict[str, Any]:
    print("Skip reason:")
    for key, value in SKIP_REASONS.items():
        print(f"  {key}. {value}")
    while True:
        reason_input = input("Choose reason [1-4]: ").strip()
        if reason_input in SKIP_REASONS:
            reason = SKIP_REASONS[reason_input]
            break
        print("Enter 1, 2, 3, or 4.")

    notes = clean_optional_input("Notes (optional): ")
    default_split = default_split_for_job(pair.job["job_id"])
    split = prompt_split_override(default_split, prompt_prefix="Split override for record-keeping")
    return {
        "job_id": pair.job["job_id"],
        "resume_id": pair.candidate["resume_id"],
        "reason": reason,
        "split": split,
        "source": source,
        "notes": notes,
        "sample_source": pair.sample_source,
        "job_title": pair.job["job_title"],
        "candidate_name": pair.candidate.get("name"),
        "source_filename": pair.candidate["profile_json"].get("source_filename"),
    }


def load_excluded_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        job_id = str(payload["job_id"]).strip()
        resume_id = str(payload["resume_id"]).strip()
        if not job_id or not resume_id:
            raise ValueError(f"Invalid excluded label at {path}:{line_number}")
        keys.add((job_id, resume_id))
    return keys


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def prompt_split_override(default_split: str, prompt_prefix: str = "Split override") -> str:
    while True:
        raw = input(f"{prompt_prefix} [train/validation/test] (Enter for default={default_split}): ").strip()
        try:
            return normalize_split(raw) or default_split
        except ValueError:
            print("Unsupported split. Enter train, validation, test, or press Enter.")


def truncate_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def format_list(values: list[Any]) -> str:
    if not values:
        return "(none)"
    return ", ".join(str(value) for value in values)


def clean_optional_input(prompt: str) -> str | None:
    value = input(prompt).strip()
    return value or None


if __name__ == "__main__":
    raise SystemExit(main())
