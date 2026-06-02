#!/usr/bin/env python3
"""mcp-outbound-safety v2 · HTTP boundary for rules-only response safety."""

from __future__ import annotations

import json
import queue
import sys
import threading
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import async_catch  # noqa: E402
import classifier  # noqa: E402

DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 9000
DEFAULT_HTTP_MAX_BODY_BYTES = 1_048_576
ASYNC_CATCH_QUEUE_MAXSIZE = 256
OUTBOUND_CATEGORIES = ("phi_reflow", "harmful", "hallucination")


def _default_phi_scan(_text: str, _context: dict[str, object]) -> classifier.PhiScanResult:
    return classifier.PhiScanResult(has_phi=False, score=0.0)


PHI_SCAN = _default_phi_scan

_ASYNC_CATCH_QUEUE: queue.Queue[tuple[str, bool]] = queue.Queue(maxsize=ASYNC_CATCH_QUEUE_MAXSIZE)
_ASYNC_CATCH_LOCK = threading.Lock()
_ASYNC_CATCH_WORKER: threading.Thread | None = None
_ASYNC_CATCH_COUNTERS = {
    "processed": 0,
    "caught": 0,
    "dropped": 0,
}
_ASYNC_CATCH_RING: deque[dict[str, object]] = deque(maxlen=256)


def _default_async_sink(event: dict[str, object]) -> None:
    _ASYNC_CATCH_RING.append(dict(event))


ASYNC_SINK = _default_async_sink


def _ensure_async_catch_worker() -> None:
    global _ASYNC_CATCH_WORKER
    with _ASYNC_CATCH_LOCK:
        if _ASYNC_CATCH_WORKER is not None and _ASYNC_CATCH_WORKER.is_alive():
            return
        worker = threading.Thread(target=_async_catch_worker_loop, daemon=True)
        worker.start()
        _ASYNC_CATCH_WORKER = worker


def _async_catch_worker_loop() -> None:
    while True:
        try:
            text, inline_flagged_phi = _ASYNC_CATCH_QUEUE.get()
        except Exception:
            continue

        try:
            _ASYNC_CATCH_COUNTERS["processed"] += 1
            if not inline_flagged_phi:
                findings = async_catch.scan_missed(text)
                for finding in findings:
                    try:
                        ASYNC_SINK(finding.to_event_dict())
                        _ASYNC_CATCH_COUNTERS["caught"] += 1
                    except Exception:
                        continue
        except Exception:
            continue
        finally:
            try:
                _ASYNC_CATCH_QUEUE.task_done()
            except Exception:
                pass


def health() -> dict[str, Any]:
    return {
        "status": "ok-v2",
        "backend": "rules-only",
        "max_response_chars": classifier.MAX_RESPONSE_CHARS,
        "categories": list(OUTBOUND_CATEGORIES),
        "async_catch": {
            "processed": _ASYNC_CATCH_COUNTERS["processed"],
            "caught": _ASYNC_CATCH_COUNTERS["caught"],
            "dropped": _ASYNC_CATCH_COUNTERS["dropped"],
            "queue_depth": _ASYNC_CATCH_QUEUE.qsize(),
        },
    }


class _OutboundSafetyHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _ensure_async_catch_worker()


class _OutboundSafetyHTTPHandler(BaseHTTPRequestHandler):
    server_version = "MedHarnessOutboundSafetyHTTP"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "msg": message}})

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

    def _handle_scan(self) -> None:
        try:
            payload = self._read_json_body()
        except Exception:
            self._error(HTTPStatus.BAD_REQUEST, "bad_request", "invalid JSON request")
            return

        try:
            response_text = payload.get("text", payload.get("payload", ""))
            if not isinstance(response_text, str):
                response_text = json.dumps(response_text, ensure_ascii=False)
            context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
            result = classifier.classify(
                response_text,
                context,
                {str(key): str(value) for key, value in policy.items()},
                phi_scan=PHI_SCAN,
            )
        except Exception:
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "outbound_safety_failed_closed",
                "outbound safety failed closed",
            )
            return

        self._send_json(HTTPStatus.OK, result.to_dict())
        self._enqueue_async_catch(response_text, _inline_flagged_phi(result))

    def _enqueue_async_catch(self, response_text: str, inline_flagged_phi: bool) -> None:
        try:
            _ensure_async_catch_worker()
            _ASYNC_CATCH_QUEUE.put_nowait((response_text, inline_flagged_phi))
        except queue.Full:
            _ASYNC_CATCH_COUNTERS["dropped"] += 1
        except Exception:
            _ASYNC_CATCH_COUNTERS["dropped"] += 1

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self._handle_health()
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/scan":
            self._handle_scan()
            return
        self._error(HTTPStatus.NOT_FOUND, "not_found", "route not found")

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _parse_serve_args(argv: list[str]) -> tuple[str, int]:
    host = DEFAULT_HTTP_HOST
    port = DEFAULT_HTTP_PORT
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--http":
            index += 1
            continue
        if arg == "--host":
            if index + 1 >= len(argv):
                raise ValueError("--host requires a value")
            host = argv[index + 1]
            index += 2
            continue
        if arg == "--port":
            if index + 1 >= len(argv):
                raise ValueError("--port requires a value")
            try:
                port = int(argv[index + 1])
            except ValueError as exc:
                raise ValueError("invalid --port value") from exc
            index += 2
            continue
        raise ValueError(f"unknown serve option: {arg}")
    return host, port


def _serve_http(host: str, port: int) -> int:
    _ensure_async_catch_worker()
    server = _OutboundSafetyHTTPServer((host, port), _OutboundSafetyHTTPHandler)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


def _inline_flagged_phi(result: classifier.Decision) -> bool:
    return any(item.type == "phi_reflow" for item in result.classifications)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        try:
            host, port = _parse_serve_args(sys.argv[2:])
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
        return _serve_http(host, port)

    if len(sys.argv) > 1 and sys.argv[1] == "health":
        print(json.dumps(health(), ensure_ascii=False))
        return 0

    if len(sys.argv) == 1:
        print(json.dumps(health(), ensure_ascii=False))
        return 0

    print(json.dumps({"error": "unknown command"}), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
