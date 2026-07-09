from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ats_parser import __version__
from ats_parser.config import load_postgres_settings
from ats_parser.extractors import SUPPORTED_EXTENSIONS
from ats_parser.extractors import extract_text
from ats_parser.models import ResumeProfile
from ats_parser.parser import ResumeParser
from ats_parser.persistence import PostgresProfileRepository
from ats_parser.reporting import RunQualityTracker


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


@dataclass
class ProcessedResumeResult:
    profile_path: Path
    skipped: bool
    persisted: bool
    profile: ResumeProfile | None = None


@dataclass
class ParserRunResult:
    processed_count: int
    persisted_count: int
    failed_count: int
    failures: list[dict[str, str]]
    manifest_path: Path


def process_resume_file(
    path: Path,
    output_dir: Path,
    parser: ResumeParser,
    overwrite: bool = False,
    repository: PostgresProfileRepository | None = None,
    connection=None,
) -> ProcessedResumeResult:
    profiles_dir = output_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    target = profiles_dir / f"{path.stem}.json"
    if target.exists() and not overwrite:
        return ProcessedResumeResult(profile_path=target, skipped=True, persisted=False)

    text, warnings = extract_text(path)
    profile = parser.parse_file(path, text, warnings)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(profile.to_dict(), handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    persisted = False
    if repository is not None and connection is not None:
        repository.upsert_profile(connection, profile)
        persisted = True

    return ProcessedResumeResult(
        profile_path=target,
        skipped=False,
        persisted=persisted,
        profile=profile,
    )


def run_parser_batch(
    input_dir: Path,
    output_dir: Path,
    env_file: Path = DEFAULT_ENV_FILE,
    limit: int | None = None,
    overwrite: bool = False,
    verbose: bool = False,
    persist_postgres: bool = False,
    postgres_schema: str = "public",
    postgres_table: str = "candidate_profiles",
) -> ParserRunResult:
    files = discover_resume_files(input_dir)
    if limit is not None:
        files = files[:limit]

    if not files:
        raise RuntimeError(f"No supported resume files found in {input_dir}")

    parser = ResumeParser()
    tracker = RunQualityTracker()
    failures: list[dict[str, str]] = []
    processed = 0
    persisted = 0

    repository = None
    if persist_postgres:
        settings = load_postgres_settings(
            env_file=env_file,
            schema=postgres_schema,
            table=postgres_table,
        )
        repository = PostgresProfileRepository(settings)

    connection_manager = repository.connect() if repository is not None else None
    connection = connection_manager.__enter__() if connection_manager is not None else None
    if repository is not None and connection is not None:
        repository.ensure_schema(connection)

    try:
        for path in files:
            try:
                result = process_resume_file(
                    path=path,
                    output_dir=output_dir,
                    parser=parser,
                    overwrite=overwrite,
                    repository=repository,
                    connection=connection,
                )
                if result.skipped:
                    if verbose:
                        print(f"Skipping existing profile: {result.profile_path}")
                    continue

                tracker.record(result.profile)
                processed += 1
                if result.persisted:
                    persisted += 1
                if verbose:
                    print(f"Parsed {path.name} -> {result.profile_path}")
            except Exception as exc:  # noqa: BLE001
                failures.append({"file": str(path), "error": str(exc)})
                print(f"Failed to parse {path}: {exc}")
    finally:
        if connection_manager is not None:
            connection_manager.__exit__(None, None, None)

    manifest_path = write_manifest(
        input_dir=input_dir,
        output_dir=output_dir,
        processed=processed,
        persisted=persisted,
        failures=failures,
        tracker=tracker,
    )
    return ParserRunResult(
        processed_count=processed,
        persisted_count=persisted,
        failed_count=len(failures),
        failures=failures,
        manifest_path=manifest_path,
    )


def write_manifest(
    input_dir: Path,
    output_dir: Path,
    processed: int,
    persisted: int,
    failures: list[dict[str, str]],
    tracker: RunQualityTracker,
) -> Path:
    manifest_path = output_dir / "manifest.json"
    manifest = {
        "parser_version": __version__,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "processed_count": processed,
        "persisted_count": persisted,
        "failed_count": len(failures),
        "failures": failures,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "quality_summary": tracker.to_dict(),
    }
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    return manifest_path


def discover_resume_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
