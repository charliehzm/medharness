#!/usr/bin/env python3
"""Tiny stdlib mock OpenAI/Anthropic-compatible upstream server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 18080
DEFAULT_HTTP_MAX_BODY_BYTES = 1_048_576

MOCK_REPLY_TEXT = "[mock-upstream] synthetic reply"
DEFAULT_MODEL = "mock-model"
CHAT_COMPLETION_ID = "chatcmpl-mock-000000000000"
ANTHROPIC_MESSAGE_ID = "msg_mock_000000000000"
CREATED_AT = 0
EMBEDDING_VECTOR = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]

# Cumulative count of relay requests actually received (chat/messages/embeddings).
# Lets a caller verify the §D.1 DENY invariant: a denied call must reach the
# upstream ZERO times (GET /__count unchanged across the denied request).
_RELAY_COUNT_LOCK = threading.Lock()
_RELAY_COUNT = 0


def _bump_relay_count() -> None:
    global _RELAY_COUNT
    with _RELAY_COUNT_LOCK:
        _RELAY_COUNT += 1


def relay_count() -> dict[str, int]:
    with _RELAY_COUNT_LOCK:
        return {"count": _RELAY_COUNT}


def health() -> dict[str, object]:
    return {"status": "ok", "service": "mock-upstream"}


def _model_from_payload(payload: dict[str, Any]) -> str:
    model = payload.get("model")
    if isinstance(model, str) and model:
        return model[:256]
    return DEFAULT_MODEL


def _usage() -> dict[str, int]:
    return {"prompt_tokens": 1, "completion_tokens": 5, "total_tokens": 6}


def _openai_chat_completion(model: str) -> dict[str, object]:
    return {
        "id": CHAT_COMPLETION_ID,
        "object": "chat.completion",
        "created": CREATED_AT,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": MOCK_REPLY_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": _usage(),
    }


def _openai_chat_chunks(model: str) -> list[dict[str, object]]:
    base = {
        "id": CHAT_COMPLETION_ID,
        "object": "chat.completion.chunk",
        "created": CREATED_AT,
        "model": model,
    }
    return [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
        {
            **base,
            "choices": [
                {"index": 0, "delta": {"content": MOCK_REPLY_TEXT}, "finish_reason": None}
            ],
        },
        {
            **base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": _usage(),
        },
    ]


def _anthropic_message(model: str) -> dict[str, object]:
    return {
        "id": ANTHROPIC_MESSAGE_ID,
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": MOCK_REPLY_TEXT}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 5},
    }


def _embeddings(model: str) -> dict[str, object]:
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": list(EMBEDDING_VECTOR), "index": 0}],
        "model": model,
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }


def _models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": DEFAULT_MODEL,
                "object": "model",
                "created": CREATED_AT,
                "owned_by": "mock-upstream",
            },
            {
                "id": "mock-embedding-model",
                "object": "model",
                "created": CREATED_AT,
                "owned_by": "mock-upstream",
            },
        ],
    }


class MockUpstreamHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class MockUpstreamHTTPHandler(BaseHTTPRequestHandler):
    server_version = "MedHarnessMockUpstreamHTTP"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, chunks: list[dict[str, object]]) -> None:
        parts = [
            f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
            for chunk in chunks
        ]
        parts.append("data: [DONE]\n\n")
        body = "".join(parts).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            raise ValueError("missing content length")
        try:
            content_length = int(length_header)
        except ValueError as exc:
            raise ValueError("invalid content length") from exc
        if content_length < 0 or content_length > DEFAULT_HTTP_MAX_BODY_BYTES:
            raise ValueError("request body too large")
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            raise ValueError("request body truncated")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _handle_health(self) -> None:
        self._send_json(HTTPStatus.OK, health())

    def _handle_models(self) -> None:
        self._send_json(HTTPStatus.OK, _models())

    def _handle_chat_completions(self) -> None:
        _bump_relay_count()
        try:
            payload = self._read_json_body()
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return
        model = _model_from_payload(payload)
        if payload.get("stream") is True:
            self._send_sse(_openai_chat_chunks(model))
            return
        self._send_json(HTTPStatus.OK, _openai_chat_completion(model))

    def _handle_messages(self) -> None:
        _bump_relay_count()
        try:
            payload = self._read_json_body()
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return
        self._send_json(HTTPStatus.OK, _anthropic_message(_model_from_payload(payload)))

    def _handle_embeddings(self) -> None:
        _bump_relay_count()
        try:
            payload = self._read_json_body()
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return
        self._send_json(HTTPStatus.OK, _embeddings(_model_from_payload(payload)))

    def do_GET(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/health":
                self._handle_health()
                return
            if path == "/__count":
                self._send_json(HTTPStatus.OK, relay_count())
                return
            if path == "/v1/models":
                self._handle_models()
                return
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "mock upstream failed")

    def do_POST(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/v1/chat/completions":
                self._handle_chat_completions()
                return
            if path == "/v1/messages":
                self._handle_messages()
                return
            if path == "/v1/embeddings":
                self._handle_embeddings()
                return
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "mock upstream failed")

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        status = HTTPStatus.OK if path == "/health" else HTTPStatus.NOT_FOUND
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _default_port() -> int:
    raw_port = os.environ.get("PORT")
    if not raw_port:
        return DEFAULT_HTTP_PORT
    try:
        return int(raw_port)
    except ValueError as exc:
        raise ValueError("invalid PORT value") from exc


def _parse_serve_args(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the MedHarness mock upstream server.")
    parser.add_argument("--port", type=int, default=_default_port())
    args = parser.parse_args(argv)
    return args.port


def _serve_http(port: int) -> int:
    server = MockUpstreamHTTPServer((DEFAULT_HTTP_HOST, port), MockUpstreamHTTPHandler)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        print(json.dumps(health(), ensure_ascii=False, separators=(",", ":")))
        return 0

    try:
        port = _parse_serve_args(sys.argv[1:])
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    return _serve_http(port)


if __name__ == "__main__":
    sys.exit(main())
