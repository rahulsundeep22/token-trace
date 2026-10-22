"""Local dashboard server (stdlib only, loopback only)."""

from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import db_path as default_db_path
from .config import load_config, save_config
from .db import connect
from .query import summary
from .scan import scan_all

WEB_DIR = Path(__file__).parent / "web"
_TOKEN = secrets.token_urlsafe(24)


class State:
    def __init__(self, config: dict):
        self.config = config
        self.lock = threading.Lock()
        self.last_scan: dict | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "TokenTrace/1.0"

    def log_message(self, format, *args):  # noqa: A002
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int = 500) -> None:
        self._json({"error": message}, status)

    def _authorized(self) -> bool:
        return self.headers.get("X-TT-Token") == _TOKEN

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            path = WEB_DIR / "dashboard.html"
            if not path.exists():
                self._error("dashboard.html is missing", 500)
                return
            html = path.read_text(encoding="utf-8")
            bootstrap = {
                "token": _TOKEN,
                "version": "1.0",
                "configPath": str(Path.home() / ".tokentrace" / "config.json"),
            }
            html = html.replace("__TT_BOOTSTRAP__", json.dumps(bootstrap))
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/health":
            self._json({"ok": True, "version": "1.0"})
            return

        if parsed.path == "/api/summary":
            params = parse_qs(parsed.query)
            days_raw = (params.get("days") or ["30"])[0]
            try:
                days = 0 if days_raw == "all" else max(1, min(int(days_raw), 3650))
            except ValueError:
                days = 30
            source = (params.get("source") or [""])[0] or None
            account = (params.get("account") or [""])[0] or None
            model = (params.get("model") or [""])[0] or None
            state: State = self.server.state
            try:
                conn = connect(default_db_path())
                try:
                    payload = summary(
                        conn,
                        days=days,
                        source=source,
                        account=account,
                        model=model,
                        config=state.config,
                    )
                finally:
                    conn.close()
                self._json(payload)
            except Exception as exc:
                self._error(str(exc))
            return

        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        self._error("Not found", 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._authorized():
            self._error("Forbidden", 403)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            self._error("Payload too large", 413)
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._error("Invalid JSON", 400)
            return

        if parsed.path == "/api/scan":
            state: State = self.server.state
            with state.lock:
                try:
                    report = scan_all(state.config)
                    state.last_scan = report
                    self._json({"ok": True, "report": report})
                except Exception as exc:
                    self._error(str(exc))
            return

        if parsed.path == "/api/accounts":
            accounts = body.get("accounts") or {}
            if not isinstance(accounts, dict):
                self._error("accounts must be an object", 400)
                return
            state: State = self.server.state
            cleaned = {}
            for key, value in accounts.items():
                if not isinstance(key, str) or not key:
                    continue
                if not isinstance(value, str):
                    value = str(value)
                value = value.strip()
                if value:
                    cleaned[key] = value[:120]
            state.config["accounts"] = cleaned
            save_config({k: v for k, v in state.config.items() if not k.startswith("_")})
            self._json({"ok": True, "accounts": cleaned})
            return

        self._error("Not found", 404)


def serve(config: dict, *, host: str = "127.0.0.1", port: int = 8787, open_browser: bool = True,
          scan_interval: int = 120, verbose: bool = False) -> None:
    state = State(config)
    httpd = None
    chosen_port = port
    for attempt in range(20):
        try:
            httpd = ThreadingHTTPServer((host, chosen_port), Handler)
            break
        except OSError:
            chosen_port += 1
    if httpd is None:
        raise RuntimeError(f"Could not bind a port in {port}-{port + 19}")
    httpd.state = state  # type: ignore[attr-defined]
    httpd.verbose = verbose  # type: ignore[attr-defined]
    url = f"http://{host}:{chosen_port}/"
    print(f"\n  TokenTrace dashboard: {url}")
    print("  Local only. Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    def auto_scan():
        while True:
            time.sleep(max(scan_interval, 30))
            try:
                with state.lock:
                    state.last_scan = scan_all(state.config)
            except Exception:
                pass

    if scan_interval:
        threading.Thread(target=auto_scan, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
