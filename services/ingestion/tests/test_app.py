from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.requests import Request

from ats_ingestion.app import create_app
from ats_ingestion.config import IngestionSettings
from ats_ingestion.storage import LocalResumeStorage


class FakePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def publish(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


class IngestionAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = IngestionSettings(upload_dir=Path(self.temp_dir.name))
        self.publisher = FakePublisher()
        self.app = create_app(
            settings=settings,
            storage=LocalResumeStorage(settings.upload_dir),
            publisher=self.publisher,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_upload_resume_persists_file_and_publishes_event(self) -> None:
        payload = self.call_route(
            "/uploads/resumes",
            body=b"sample resume content",
            headers={"x-filename": "candidate-one.pdf"},
        )

        stored_path = Path(payload["source_path"])
        self.assertEqual(payload["resume_id"], "candidate-one")
        self.assertTrue(stored_path.exists())
        self.assertEqual(stored_path.read_bytes(), b"sample resume content")
        self.assertEqual(self.publisher.payloads[0]["resume_id"], "candidate-one")

    def test_upload_resume_rejects_invalid_extension(self) -> None:
        with self.assertRaises(HTTPException) as context:
            self.call_route(
                "/uploads/resumes",
                body=b"resume body",
                headers={"x-filename": "candidate-one.exe"},
            )
        self.assertEqual(context.exception.status_code, 400)

    def test_upload_resume_honors_resume_id_override(self) -> None:
        payload = self.call_route(
            "/uploads/resumes",
            body=b"resume body",
            headers={
                "x-filename": "candidate-one.pdf",
                "x-resume-id": "candidate_override_01",
            },
        )

        self.assertEqual(payload["resume_id"], "candidate_override_01")
        self.assertEqual(self.publisher.payloads[0]["resume_id"], "candidate_override_01")

    def call_route(self, path: str, body: bytes, headers: dict[str, str]) -> dict[str, object]:
        route = next(route for route in self.app.routes if getattr(route, "path", None) == path)
        request = build_request(app=self.app, path=path, body=body, headers=headers)
        return asyncio.run(route.endpoint(request))


def build_request(app, path: str, body: bytes, headers: dict[str, str]) -> Request:
    raw_headers = [(key.lower().encode("utf-8"), value.encode("utf-8")) for key, value in headers.items()]
    if not any(key == b"content-length" for key, _ in raw_headers):
        raw_headers.append((b"content-length", str(len(body)).encode("utf-8")))

    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    return Request(
        {
            "type": "http",
            "app": app,
            "headers": raw_headers,
            "method": "POST",
            "path": path,
            "query_string": b"",
        },
        receive=receive,
    )


if __name__ == "__main__":
    unittest.main()
