from __future__ import annotations

import argparse
from pathlib import Path

from ats_embedding.cli import DEFAULT_ARTIFACTS_DIR
from ats_embedding.cli import DEFAULT_ENV_FILE
from ats_embedding.cli import DEFAULT_JD_DIR
from ats_embedding.embeddings import DEFAULT_MODEL_NAME
from ats_embedding.embeddings import EmbeddingGenerator
from ats_embedding.pipeline import run_incremental_embedding_pipeline
from ats_shared.events import EventConsumer
from ats_shared.events import EventProducer
from ats_shared.events import RESUME_EMBEDDED_TOPIC
from ats_shared.events import RESUME_PARSED_TOPIC
from ats_shared.events import load_kafka_settings


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume resume.parsed events and refresh embeddings.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--jd-dir", type=Path, default=DEFAULT_JD_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--group-id", default="ats-embedding-consumer")
    parser.add_argument("--input-topic", default=RESUME_PARSED_TOPIC)
    parser.add_argument("--output-topic", default=RESUME_EMBEDDED_TOPIC)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    kafka_settings = load_kafka_settings(args.env_file, group_id=args.group_id)
    consumer = EventConsumer(kafka_settings, [args.input_topic], client_id="ats-embedding-consumer")
    producer = EventProducer(kafka_settings, client_id="ats-embedding-producer")
    generator = EmbeddingGenerator(args.model_name)

    print(
        f"Embedding consumer is listening on {args.input_topic} and will publish to {args.output_topic}."
    )
    try:
        while True:
            event = consumer.poll(timeout_seconds=1.0)
            if event is None:
                continue

            try:
                resume_id = event.payload.get("resume_id")
                if not resume_id:
                    raise RuntimeError("resume.parsed event is missing resume_id.")

                result = run_incremental_embedding_pipeline(
                    env_file=args.env_file,
                    jd_dir=args.jd_dir.resolve(),
                    artifacts_dir=args.artifacts_dir.resolve(),
                    resume_id=resume_id,
                    model_name=args.model_name,
                    top_k=args.top_k,
                    generator=generator,
                )
                producer.publish(
                    topic=args.output_topic,
                    key=resume_id,
                    payload={
                        "resume_id": resume_id,
                        "affected_job_ids": result.affected_job_ids,
                        "model_name": result.model_name,
                        "top_k": result.top_k,
                    },
                )
                producer.flush()
                consumer.commit(event)
                print(
                    f"Updated embedding for {resume_id} and refreshed retrievals for "
                    f"{len(result.affected_job_ids)} job(s); published {args.output_topic}."
                )
            except Exception as exc:  # noqa: BLE001
                print(f"Failed to process embedding event at offset {event.offset}: {exc}")
    except KeyboardInterrupt:
        print("Stopping embedding consumer.")
    finally:
        producer.flush()
        consumer.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
