"""Claude Code adapter (JSONL transcripts under ~/.claude/projects)."""

from __future__ import annotations

import json
from pathlib import Path

from ..pricing import pretty_model
from ..util import clean_title, parse_iso_ms
from .base import Event, Instance, basename

SOURCE = "claude_code"
SOURCE_LABEL = "Claude Code"


def _account_key() -> str:
    for path in (Path.home() / ".claude.json", Path.home() / ".config" / "claude" / "claude.json"):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            email = (data.get("oauthAccount") or {}).get("emailAddress")
            if email:
                return str(email).lower()
        except Exception:
            continue
    return SOURCE


def discover(extra: list[Path]) -> list[Instance]:
    dirs = [
        Path.home() / ".claude" / "projects",
        Path.home() / ".config" / "claude" / "projects",
    ]
    dirs.extend(extra)
    instances: list[Instance] = []
    seen: set[str] = set()
    account = _account_key()
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.jsonl")):
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            instances.append(
                Instance(
                    source=SOURCE,
                    source_label=SOURCE_LABEL,
                    surface="CLI",
                    account_key=account,
                    path=str(path),
                    detail="Claude Code transcript",
                )
            )
    return instances


def _user_text(message) -> str | None:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            if parts:
                return " ".join(parts)
    return None


def scan(instance: Instance) -> tuple[list[Event], list[str]]:
    events: dict[str, Event] = {}
    errors: list[str] = []
    title: str | None = None
    session_id = Path(instance.path).stem
    project = None
    try:
        with open(instance.path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("sessionId"):
                    session_id = row["sessionId"]
                if row.get("cwd"):
                    project = basename(row["cwd"])
                row_type = row.get("type")
                if row_type == "user" and title is None:
                    title = clean_title(_user_text(row.get("message")))
                    continue
                if row_type != "assistant":
                    continue
                message = row.get("message") or {}
                usage = message.get("usage") or {}
                if not usage:
                    continue
                input_tokens = int(usage.get("input_tokens") or 0)
                output_tokens = int(usage.get("output_tokens") or 0)
                cache_read = int(usage.get("cache_read_input_tokens") or 0)
                cache_write = int(usage.get("cache_creation_input_tokens") or 0)
                reasoning = int(usage.get("reasoning_tokens") or 0)
                message_id = message.get("id") or row.get("uuid") or f"line:{len(events)}"
                cost = row.get("costUSD")
                if cost is None:
                    cost = row.get("cost")
                existing = events.get(message_id)
                if existing:
                    existing.input = max(existing.input, input_tokens)
                    existing.output = max(existing.output, output_tokens)
                    existing.cache_read = max(existing.cache_read, cache_read)
                    existing.cache_write = max(existing.cache_write, cache_write)
                    existing.reasoning = max(existing.reasoning, reasoning)
                    continue
                model = message.get("model") or row.get("model")
                events[message_id] = Event(
                    source=SOURCE,
                    source_label=SOURCE_LABEL,
                    surface=instance.surface,
                    account_key=instance.account_key,
                    session_id=session_id,
                    native_id=message_id,
                    ts=parse_iso_ms(row.get("timestamp")) or 0,
                    model=model,
                    model_label=pretty_model(model) if model else None,
                    session_title=title,
                    project=project,
                    input=input_tokens,
                    output=output_tokens,
                    reasoning=reasoning,
                    cache_read=cache_read,
                    cache_write=cache_write,
                    cost=float(cost) if cost is not None else None,
                    cost_kind="exact" if cost is not None else "estimated",
                    price_provider="anthropic",
                    ref=instance.path,
                )
    except Exception as exc:
        errors.append(f"{instance.path}: {exc}")
    for event in events.values():
        if event.session_title is None:
            event.session_title = title or project
    return [e for e in events.values() if e.has_tokens()], errors
