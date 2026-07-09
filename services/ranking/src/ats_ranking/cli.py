from __future__ import annotations

import argparse
from pathlib import Path

from ats_ranking.pipeline import run_ranking_pipeline


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_ARTIFACTS_DIR = REPO_ROOT / "data" / "processed" / "ranking"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank retrieved candidates for each job description.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--top-n", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        result = run_ranking_pipeline(
            env_file=args.env_file,
            artifacts_dir=args.artifacts_dir.resolve(),
            top_n=args.top_n,
        )
    except RuntimeError as exc:
        print(exc)
        return 1

    print(
        f"Ranked candidates for {result.job_count} job(s). "
        f"Total ranked candidates: {result.ranked_candidate_count}."
    )
    return 0
