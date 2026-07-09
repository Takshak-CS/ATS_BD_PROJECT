from __future__ import annotations

import argparse
from pathlib import Path

from ats_parser.pipeline import run_parser_batch


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "raw" / "resumes"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "parser"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse resume files into structured JSON profiles.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--persist-postgres", action="store_true")
    parser.add_argument("--postgres-schema", default="public")
    parser.add_argument("--postgres-table", default="candidate_profiles")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    try:
        result = run_parser_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            env_file=args.env_file,
            limit=args.limit,
            overwrite=args.overwrite,
            verbose=args.verbose,
            persist_postgres=args.persist_postgres,
            postgres_schema=args.postgres_schema,
            postgres_table=args.postgres_table,
        )
    except RuntimeError as exc:
        print(exc)
        return 1

    print(
        f"Processed {result.processed_count} resume(s) from {input_dir} into {output_dir / 'profiles'}. "
        f"Failures: {result.failed_count}. Persisted: {result.persisted_count}."
    )
    return 1 if result.failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
