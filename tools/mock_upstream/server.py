#!/usr/bin/env python3
"""Tiny stdlib mock OpenAI/Anthropic-compatible upstream server.

Beyond the happy-path provider dialects it exposes a few X-Mock-* request
headers (with MOCK_* env fallbacks) so tests can drive the gateway's error,
latency, timeout, token-cost, and post-call (outbound-safety) paths WITHOUT any
third-party deps. These headers are inert to the real gateway. A /__count relay
counter (and /__reset) lets a caller verify the §D.1 DENY invariant — a denied
call must reach the upstream ZERO times.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
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

# Multi-vendor catalog so model×vendor matrix cases have real ids to vary.
MODEL_CATALOG = (
    ("gpt-4o", "openai"),
    ("claude-sonnet-4.6", "anthropic"),
    ("qwen-max-2026", "alibaba"),
    (DEFAULT_MODEL, "mock-upstream"),
    ("mock-embedding-model", "mock-upstream"),
)

# SYNTHETIC PHI-shaped string (NOT a real person) appended to the reply when
# X-Mock-Echo-Phi=1, so the post-call outbound-safety gate fires (the one DENY
# path where the upstream IS hit but the client still gets a generic 503).
ECHO_PHI_TEXT = " 病案号 BL-SYN-0001 身份证 110101199001011234 手机 13800138000"

MAX_INJECTED_DELAY_SECONDS = 30.0

# Cumulative count of relay requests actually received (chat/messages/embeddings).
_RELAY_COUNT_LOCK = threading.Lock()
_RELAY_COUNT = 0


def _bump_relay_count() -> None:
    global _RELAY_COUNT
    with _RELAY_COUNT_LOCK:
        _RELAY_COUNT += 1


def _reset_relay_count() -> None:
    global _RELAY_COUNT
    with _RELAY_COUNT_LOCK:
        _RELAY_COUNT = 0


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


def _reply_text(directives: dict[str, Any] | None = None) -> str:
    if directives and directives.get("echo_phi"):
        return MOCK_REPLY_TEXT + ECHO_PHI_TEXT
    return MOCK_REPLY_TEXT


def _usage(directives: dict[str, Any] | None = None) -> dict[str, int]:
    directives = directives or {}
    prompt = directives.get("prompt_tokens")
    completion = directives.get("completion_tokens")
    prompt = 1 if prompt is None else int(prompt)
    completion = 5 if completion is None else int(completion)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def _openai_chat_completion(model: str, directives: dict[str, Any] | None = None) -> dict[str, object]:
    return {
        "id": CHAT_COMPLETION_ID,
        "object": "chat.completion",
        "created": CREATED_AT,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": _reply_text(directives)},
                "finish_reason": "stop",
            }
        ],
        "usage": _usage(directives),
    }


def _openai_chat_chunks(model: str, directives: dict[str, Any] | None = None) -> list[dict[str, object]]:
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
                {"index": 0, "delta": {"content": _reply_text(directives)}, "finish_reason": None}
            ],
        },
        {
            **base,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": _usage(directives),
        },
    ]


def _anthropic_message(model: str, directives: dict[str, Any] | None = None) -> dict[str, object]:
    usage = _usage(directives)
    return {
        "id": ANTHROPIC_MESSAGE_ID,
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": _reply_text(directives)}],
        "model": model,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"]},
    }


def _embeddings(model: str, directives: dict[str, Any] | None = None) -> dict[str, object]:
    usage = _usage(directives)
    return {
        "object": "list",
        "data": [{"object": "embedding", "embedding": list(EMBEDDING_VECTOR), "index": 0}],
        "model": model,
        "usage": {"prompt_tokens": usage["prompt_tokens"], "total_tokens": usage["prompt_tokens"]},
    }


def _models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "created": CREATED_AT, "owned_by": vendor}
            for model_id, vendor in MODEL_CATALOG
        ],
    }


def _int_directive(headers: Any, name: str, env: str, default: int | None) -> int | None:
    raw = headers.get(name)
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get(env)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def _flag_directive(headers: Any, name: str, env: str) -> bool:
    raw = headers.get(name)
    if raw is None or str(raw).strip() == "":
        raw = os.environ.get(env)
    return str(raw).strip().lower() in {"1", "true", "yes", "on"} if raw is not None else False


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

    def _directives(self) -> dict[str, Any]:
        h = self.headers
        return {
            "latency_ms": _int_directive(h, "X-Mock-Latency-Ms", "MOCK_LATENCY_MS", 0) or 0,
            "hang_s": _int_directive(h, "X-Mock-Hang", "MOCK_HANG_S", 0) or 0,
            "status": _int_directive(h, "X-Mock-Status", "MOCK_STATUS", None),
            "echo_phi": _flag_directive(h, "X-Mock-Echo-Phi", "MOCK_ECHO_PHI"),
            "prompt_tokens": _int_directive(h, "X-Mock-Prompt-Tokens", "MOCK_PROMPT_TOKENS", None),
            "completion_tokens": _int_directive(h, "X-Mock-Completion-Tokens", "MOCK_COMPLETION_TOKENS", None),
        }

    def _relay_pre(self, directives: dict[str, Any]) -> bool:
        """Count the hit, apply injected latency/hang, then optionally short-circuit
        with an injected error status. Returns True if a response was already sent."""
        _bump_relay_count()
        delay = directives["latency_ms"] / 1000.0 + float(directives["hang_s"])
        if delay > 0:
            time.sleep(min(delay, MAX_INJECTED_DELAY_SECONDS))
        if directives["status"] is not None:
            try:
                status = HTTPStatus(int(directives["status"]))
            except ValueError:
                status = HTTPStatus.INTERNAL_SERVER_ERROR
            self._error(status, "mock_injected_error", f"mock injected HTTP {int(status)}")
            return True
        return False

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
        directives = self._directives()
        if self._relay_pre(directives):
            return
        try:
            payload = self._read_json_body()
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return
        model = _model_from_payload(payload)
        if payload.get("stream") is True:
            self._send_sse(_openai_chat_chunks(model, directives))
            return
        self._send_json(HTTPStatus.OK, _openai_chat_completion(model, directives))

    def _handle_messages(self) -> None:
        directives = self._directives()
        if self._relay_pre(directives):
            return
        try:
            payload = self._read_json_body()
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return
        self._send_json(HTTPStatus.OK, _anthropic_message(_model_from_payload(payload), directives))

    def _handle_embeddings(self) -> None:
        directives = self._directives()
        if self._relay_pre(directives):
            return
        try:
            payload = self._read_json_body()
        except ValueError:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return
        self._send_json(HTTPStatus.OK, _embeddings(_model_from_payload(payload), directives))

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
            if path == "/__reset":
                _reset_relay_count()
                self._send_json(HTTPStatus.OK, {"count": 0, "reset": True})
                return
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
