from __future__ import annotations

import argparse
from pathlib import Path

from ats_ranking.cli import DEFAULT_ARTIFACTS_DIR
from ats_ranking.cli import DEFAULT_ENV_FILE
from ats_ranking.pipeline import run_incremental_ranking_pipeline
from ats_shared.events import CANDIDATE_RANKED_TOPIC
from ats_shared.events import EventConsumer
from ats_shared.events import EventProducer
from ats_shared.events import RESUME_EMBEDDED_TOPIC
from ats_shared.events import load_kafka_settings


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume resume.embedded events and refresh rankings.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--group-id", default="ats-ranking-consumer")
    parser.add_argument("--input-topic", default=RESUME_EMBEDDED_TOPIC)
    parser.add_argument("--output-topic", default=CANDIDATE_RANKED_TOPIC)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    kafka_settings = load_kafka_settings(args.env_file, group_id=args.group_id)
    consumer = EventConsumer(kafka_settings, [args.input_topic], client_id="ats-ranking-consumer")
    producer = EventProducer(kafka_settings, client_id="ats-ranking-producer")

    print(
        f"Ranking consumer is listening on {args.input_topic} and will publish to {args.output_topic}."
    )
    try:
        while True:
            event = consumer.poll(timeout_seconds=1.0)
            if event is None:
                continue

            try:
                resume_id = event.payload.get("resume_id")
                if not resume_id:
                    raise RuntimeError("resume.embedded event is missing resume_id.")
                affected_job_ids = event.payload.get("affected_job_ids")

                result = run_incremental_ranking_pipeline(
                    env_file=args.env_file,
                    artifacts_dir=args.artifacts_dir.resolve(),
                    resume_id=resume_id,
                    top_n=args.top_n,
                    job_ids=affected_job_ids,
                )
                producer.publish(
                    topic=args.output_topic,
                    key=resume_id,
                    payload={
                        "resume_id": resume_id,
                        "job_ids": result.job_ids,
                        "job_count": result.job_count,
                        "ranked_candidate_count": result.ranked_candidate_count,
                        "top_n": result.top_n,
                    },
                )
                producer.flush()
                consumer.commit(event)
                print(
                    f"Updated rankings for {resume_id} across {result.job_count} job(s) "
                    f"and published {args.output_topic}."
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Failed to process ranking event at offset {event.offset}: {exc}")
    except KeyboardInterrupt:
        print("Stopping ranking consumer.")
    finally:
        producer.flush()
        consumer.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
