from __future__ import annotations

import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from min_agent.permission_broker import PermissionAlreadyResolved, PermissionNotFound


class WebAgentHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


class WebAgentServer:
    """Serves the local Web shell and its same-origin runtime API."""

    def __init__(
        self,
        manager: Any,
        history: Any,
        key_store: Any,
        web_dir: Path,
        port: int = 8765,
    ) -> None:
        self.manager = manager
        self.history = history
        self.key_store = key_store
        self.web_dir = web_dir.resolve()
        self._server = self._make(port)
        self._thread: threading.Thread | None = None

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def url(self) -> str:
        return self.origin + "/"

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self.close()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None

    def _make(self, port: int) -> WebAgentHTTPServer:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args: Any) -> None:
                pass

            def _json(
                self,
                status: int,
                data: Any = None,
                code: str | None = None,
                message: str | None = None,
            ) -> None:
                if code is None:
                    payload = {"ok": True, "data": data}
                else:
                    payload = {
                        "ok": False,
                        "error": {"code": code, "message": message},
                    }
                raw = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _guard(self, mutating: bool = False) -> bool:
                expected_host = f"127.0.0.1:{outer._server.server_address[1]}"
                if self.headers.get("Host") != expected_host:
                    self._json(400, code="invalid_host", message="Invalid Host")
                    return False
                if mutating and self.headers.get("Origin") != outer.origin:
                    self._json(403, code="invalid_origin", message="Invalid Origin")
                    return False
                return True

            def _body(self) -> dict[str, Any]:
                if self.headers.get("Content-Type") != "application/json":
                    raise ValueError
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0 or length > 16384:
                    raise ValueError
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError
                return value

            def do_GET(self) -> None:
                if not self._guard():
                    return

                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/api/state":
                    self._json(
                        200,
                        {
                            "workspace": str(outer.manager.workspace),
                            "service_state": outer.manager.service_state(),
                            "configured": outer.key_store.is_configured(),
                            "current_run": outer.manager.current_snapshot(),
                        },
                    )
                    return
                if path == "/api/runs/current":
                    self._json(200, outer.manager.current_snapshot())
                    return
                if path == "/api/permissions/current":
                    snapshot = outer.manager.permission_broker.current()
                    data = (
                        snapshot.to_public_dict()
                        if snapshot and snapshot.status == "pending"
                        else None
                    )
                    self._json(200, data)
                    return
                if path == "/api/history":
                    self._json(200, outer.history.list_runs().to_dict())
                    return
                if path.startswith("/api/history/"):
                    try:
                        self._json(200, outer.history.load_run(path.rsplit("/", 1)[1]))
                    except FileNotFoundError:
                        self._json(404, code="not_found", message="Run not found")
                    return
                if path == "/api/runs/current/events":
                    run_id = parse_qs(parsed.query).get("run_id", [""])[0]
                    self._events(run_id)
                    return
                if path.startswith("/api/"):
                    self._json(404, code="not_found", message="Not found")
                    return

                name = "web_agent.html" if path == "/" else path.lstrip("/")
                file = (outer.web_dir / name).resolve()
                if outer.web_dir not in file.parents or not file.is_file():
                    self.send_error(404)
                    return

                raw = file.read_bytes()
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    mimetypes.guess_type(file.name)[0] or "application/octet-stream",
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _events(self, run_id: str) -> None:
                try:
                    subscription = outer.manager.subscribe(run_id)
                except LookupError:
                    self._json(404, code="not_found", message="Run not found")
                    return

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    for event in subscription.initial_events:
                        self.wfile.write(
                            f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n".encode()
                        )
                    while (event := subscription.event_queue.get()) is not None:
                        self.wfile.write(
                            f"data: {json.dumps(event.to_dict(), ensure_ascii=False)}\n\n".encode()
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    subscription.close()

            def do_PUT(self) -> None:
                if self.path != "/api/deepseek-key" or not self._guard(True):
                    return
                if outer.manager.has_active_deepseek_run():
                    self._json(
                        409,
                        code="active_deepseek_run",
                        message="DeepSeek run is active",
                    )
                    return
                try:
                    body = self._body()
                    outer.key_store.configure(body.get("api_key", ""))
                    self._json(200, {"configured": True})
                except ValueError:
                    self._json(400, code="invalid_key", message="Invalid Key")

            def do_DELETE(self) -> None:
                if self.path != "/api/deepseek-key" or not self._guard(True):
                    return
                if outer.manager.has_active_deepseek_run():
                    self._json(
                        409,
                        code="active_deepseek_run",
                        message="DeepSeek run is active",
                    )
                    return
                outer.key_store.clear()
                self._json(200, {"configured": False})

            def do_POST(self) -> None:
                if not self._guard(True):
                    return

                if self.path == "/api/runs":
                    try:
                        body = self._body()
                        if set(body) != {"goal", "decision_model"}:
                            raise ValueError
                        data = outer.manager.start_run(
                            body["goal"],
                            body["decision_model"],
                        )
                        self._json(201, data)
                    except ValueError:
                        self._json(
                            400,
                            code="invalid_request",
                            message="Invalid run request",
                        )
                    except RuntimeError as exc:
                        code = (
                            "active_run_conflict"
                            if str(exc) == "active_run_conflict"
                            else "key_not_configured"
                        )
                        self._json(409, code=code, message="Unable to start run")
                    return

                prefix = "/api/permissions/"
                if self.path.startswith(prefix) and self.path.endswith("/decision"):
                    try:
                        body = self._body()
                        permission_id = self.path[
                            len(prefix) : -len("/decision")
                        ].strip("/")
                        snapshot = outer.manager.permission_broker.resolve(
                            permission_id,
                            body.get("approved"),
                        )
                        self._json(200, snapshot.to_public_dict())
                    except ValueError:
                        self._json(
                            400,
                            code="invalid_request",
                            message="Invalid decision",
                        )
                    except PermissionNotFound:
                        self._json(
                            404,
                            code="not_found",
                            message="Permission not found",
                        )
                    except PermissionAlreadyResolved:
                        self._json(
                            409,
                            code="already_resolved",
                            message="Permission already resolved",
                        )
                    return

                self._json(404, code="not_found", message="Not found")

            def do_OPTIONS(self) -> None:
                self._json(
                    405,
                    code="method_not_allowed",
                    message="Method not allowed",
                )

        return WebAgentHTTPServer(("127.0.0.1", port), Handler)
