"""OpenAI Codex CLI adapter (JSONL rollouts under ~/.codex/sessions)."""

from __future__ import annotations

import json
from pathlib import Path

from ..pricing import pretty_model
from ..util import clean_title, parse_iso_ms
from .base import Event, Instance, basename

SOURCE = "codex"
SOURCE_LABEL = "Codex"


def discover(extra: list[Path]) -> list[Instance]:
    dirs = [
        Path.home() / ".codex" / "sessions",
        Path.home() / ".codex" / "archived_sessions",
    ]
    dirs.extend(extra)
    instances: list[Instance] = []
    seen: set[str] = set()
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
                    account_key=SOURCE,
                    path=str(path),
                    detail="Codex rollout",
                )
            )
    return instances


def _usage_from(info: dict | None) -> tuple[int, int, int, int] | None:
    if not isinstance(info, dict):
        return None
    input_tokens = int(info.get("input_tokens") or 0)
    cached = int(info.get("cached_input_tokens") or 0)
    output_tokens = int(info.get("output_tokens") or 0)
    reasoning = int(info.get("reasoning_output_tokens") or 0)
    if not (input_tokens or cached or output_tokens or reasoning):
        return None
    # Codex input_tokens includes cached input; output_tokens includes reasoning.
    fresh_input = max(0, input_tokens - cached)
    visible_output = max(0, output_tokens - reasoning)
    return fresh_input, visible_output, reasoning, cached


def scan(instance: Instance) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    session_id = Path(instance.path).stem
    project = None
    model = None
    title = None
    previous_total: dict[str, int] = {}
    counter = 0
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
                row_type = row.get("type")
                payload = row.get("payload") or {}
                if row_type == "session_meta":
                    session_id = payload.get("id") or session_id
                    project = basename(payload.get("cwd")) or project
                    model = payload.get("model") or model
                    title = clean_title(payload.get("instructions") or "")
                    continue
                if row_type == "turn_context":
                    model = payload.get("model") or model
                    project = basename(payload.get("cwd")) or project
                    continue
                if row_type != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
                usage = _usage_from(info.get("last_token_usage"))
                if usage is None:
                    totals = info.get("total_token_usage") or {}
                    clean_totals = {
                        "input_tokens": int(totals.get("input_tokens") or 0),
                        "cached_input_tokens": int(totals.get("cached_input_tokens") or 0),
                        "output_tokens": int(totals.get("output_tokens") or 0),
                        "reasoning_output_tokens": int(totals.get("reasoning_output_tokens") or 0),
                    }
                    delta = {}
                    for key, value in clean_totals.items():
                        delta[key] = max(0, value - previous_total.get(key, 0))
                        previous_total[key] = value
                    usage = _usage_from(delta)
                if usage is None:
                    continue
                counter += 1
                when = row.get("timestamp")
                events.append(
                    Event(
                        source=SOURCE,
                        source_label=SOURCE_LABEL,
                        surface=instance.surface,
                        account_key=instance.account_key,
                        session_id=session_id,
                        native_id=f"line:{counter}",
                        ts=parse_iso_ms(when) or 0,
                        model=model,
                        model_label=pretty_model(model) if model else None,
                        session_title=title or project,
                        project=project,
                        input=usage[0],
                        output=usage[1],
                        reasoning=usage[2],
                        cache_read=usage[3],
                        cache_write=0,
                        cost=None,
                        cost_kind="estimated",
                        price_provider="openai",
                        ref=instance.path,
                    )
                )
    except Exception as exc:
        errors.append(f"{instance.path}: {exc}")
    return [e for e in events if e.has_tokens()], errors
