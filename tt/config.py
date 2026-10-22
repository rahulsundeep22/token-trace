"""Local configuration and paths for TokenTrace."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_CONFIG = {
    "accounts": {},
    "extra_paths": {
        "antigravity": [],
        "opencode": [],
        "claude_code": [],
        "codex": [],
        "gemini_cli": [],
    },
    "pricing": {},
    "scan_interval_seconds": 120,
}


def home() -> Path:
    override = os.environ.get("TOKENTRACE_HOME")
    path = Path(override).expanduser() if override else Path.home() / ".tokentrace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return home() / "tokentrace.db"


def config_path() -> Path:
    return home() / "config.json"


def load_config() -> dict:
    path = config_path()
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in {"accounts", "extra_paths", "pricing"} and isinstance(value, dict):
                        config[key].update(value)
                    else:
                        config[key] = value
        except Exception:
            pass
    return config


def save_config(config: dict) -> None:
    path = config_path()
    fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


DEFAULT_ACCOUNT_LABELS = {
    "antigravity": "Antigravity App",
    "antigravity-ide": "Antigravity IDE",
    "antigravity-cli": "Antigravity CLI",
    "opencode": "OpenCode",
    "opencode-preview": "OpenCode Preview",
    "claude_code": "Claude Code",
    "codex": "Codex",
    "gemini_cli": "Gemini CLI",
}


def account_label(config: dict, key: str) -> str:
    configured = (config.get("accounts") or {}).get(key)
    if configured:
        return str(configured)
    if key in DEFAULT_ACCOUNT_LABELS:
        return DEFAULT_ACCOUNT_LABELS[key]
    if "@" in key:
        return key
    return key.replace("_", " ").replace("-", " ").title()


def extra_paths(config: dict, source: str) -> list[Path]:
    raw = (config.get("extra_paths") or {}).get(source) or []
    if isinstance(raw, str):
        raw = [raw]
    return [Path(p).expanduser() for p in raw]
