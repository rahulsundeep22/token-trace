"""Small shared helpers."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import unquote


def ro_uri(path: Path | str) -> str:
    """A read-only SQLite URI that survives spaces and Windows drive letters."""
    p = Path(path)
    return p.resolve().as_uri() + "?mode=ro"


def local_date(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000).astimezone().strftime("%Y-%m-%d")


def local_midnight(days_ago: int = 0) -> dt.datetime:
    now = dt.datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - dt.timedelta(days=days_ago)


def parse_iso_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return int(parsed.timestamp() * 1000)
    except Exception:
        return None


def file_uri_to_path(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"file:///[^\s\"']+", value)
    raw = match.group(0) if match else value
    raw = unquote(raw)
    raw = re.sub(r"^file:///", "", raw)
    raw = re.sub(r"^file://", "", raw)
    if re.match(r"^[a-zA-Z]:", raw):
        return raw.replace("/", "\\")
    if raw.startswith("/") and re.match(r"^/[a-zA-Z]:", raw):
        return raw[1:].replace("/", "\\")
    return raw


def clean_title(value: str | None, max_length: int = 78) -> str | None:
    if not value:
        return None
    text = "".join(ch for ch in value if ch.isprintable() or ch in "\n\t")
    text = text.replace("\ufffd", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 4:
        return None
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return None
    text = re.sub(r'^[^A-Za-z0-9"\']+', "", text)
    text = re.sub(r"^\d(?=[A-Za-z])", "", text)
    text = re.sub(r"^[A-Z]-\s+", "", text)
    if len(text) > 1 and text[0].isupper() and text[1].isupper():
        text = text[1:]
    if len(text) > 2 and text[0].isupper():
        first_word = re.match(r"[A-Za-z']+", text[1:])
        if first_word and first_word.group(0).lower() in {
            "okay", "sorry", "i", "i've", "i'm", "can", "could", "would", "how",
            "what", "why", "where", "when", "make", "create", "build", "write",
            "add", "fix", "please", "help", "find", "use", "update", "remove",
            "run", "generate", "explain", "show", "get", "let", "act", "design",
            "implement", "look", "give", "tell", "do", "is", "are", "we", "my",
            "the", "this", "that", "it", "there", "hello", "hi", "hey",
        }:
            text = text[1:].lstrip()
    if len(text) < 4:
        return None
    lowered = text.lower()
    if any(
        marker in lowered
        for marker in (
            "toolaction",
            "toolsummary",
            "absolutepath",
            "file://",
            "command(",
            "```",
            "conversation history",
            "conversation_summaries",
            "here are the conversation ids",
        )
    ):
        return None
    if text.startswith("{") or "://" in text:
        return None
    if re.search(r"\.(json|py|md|js|ts|db|png|jpg|css|html)\b", lowered):
        return None
    letters = sum(ch.isalpha() or ch.isspace() or ch in "'\"?!.,;:()[]-–—/" for ch in text)
    if letters / max(len(text), 1) < 0.72:
        return None
    if len(text) > max_length:
        cut = text[:max_length].rsplit(" ", 1)[0]
        text = (cut or text[:max_length]).rstrip(" ,.;:") + "…"
    return text
