"""Gemini CLI adapter (session JSON under ~/.gemini/tmp/*/chats)."""

from __future__ import annotations

import json
from pathlib import Path

from ..pricing import pretty_model
from ..util import clean_title, parse_iso_ms
from .base import Event, Instance, basename

SOURCE = "gemini_cli"
SOURCE_LABEL = "Gemini CLI"


def discover(extra: list[Path]) -> list[Instance]:
    roots = [Path.home() / ".gemini" / "tmp"]
    roots.extend(extra)
    instances: list[Instance] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            if "chats" not in [part.lower() for part in path.parts]:
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            instances.append(
                Instance(
                    source=SOURCE,
                    source_label=SOURCE_LABEL,
                    surface="CLI",
                    account_key=SOURCE,
                    path=str(path),
                    detail="Gemini CLI session",
                )
            )
    return instances


def _text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return " ".join(p for p in parts if p)
    return None


def scan(instance: Instance) -> tuple[list[Event], list[str]]:
    try:
        data = json.loads(Path(instance.path).read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return [], [f"{instance.path}: {exc}"]
    if not isinstance(data, dict):
        return [], []
    messages = data.get("messages") or []
    session_id = data.get("sessionId") or Path(instance.path).stem
    title = None
    events: list[Event] = []
    for index, row in enumerate(messages):
        if not isinstance(row, dict):
            continue
        if row.get("type") == "user" and title is None:
            title = clean_title(_text(row.get("content")))
        tokens = row.get("tokens") or {}
        if not isinstance(tokens, dict):
            continue
        input_tokens = int(tokens.get("input") or 0)
        output_tokens = int(tokens.get("output") or 0)
        reasoning = int(tokens.get("thoughts") or tokens.get("reasoning") or 0)
        cache_read = int(tokens.get("cached") or 0)
        tool_tokens = int(tokens.get("tool") or 0)
        if not (input_tokens or output_tokens or reasoning or cache_read or tool_tokens):
            continue
        model = row.get("model") or data.get("model")
        event = Event(
            source=SOURCE,
            source_label=SOURCE_LABEL,
            surface=instance.surface,
            account_key=instance.account_key,
            session_id=session_id,
            native_id=str(row.get("id") or f"msg:{index}"),
            ts=parse_iso_ms(row.get("timestamp")) or parse_iso_ms(data.get("startTime")) or 0,
            model=model,
            model_label=pretty_model(model) if model else None,
            session_title=title or basename(data.get("cwd")),
            project=basename(data.get("cwd")),
            input=input_tokens,
            output=output_tokens,
            reasoning=reasoning,
            cache_read=cache_read,
            cache_write=0,
            cost=None,
            cost_kind="estimated",
            price_provider="google",
            ref=instance.path,
        )
        events.append(event)
    if title:
        for event in events:
            event.session_title = event.session_title or title
    return events, []
