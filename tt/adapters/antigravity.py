"""Antigravity adapter (App, IDE and CLI conversation databases).

Antigravity stores one SQLite database per conversation. Token accounting lives
in protobuf blobs inside `gen_metadata` (and, on some builds, `steps`). The wire
layout was cross-checked against ccusage's antigravity adapter and validated on
real local databases:

    gen_metadata.data -> field 1 (chat model message)
      field 3  model id (varint)
      field 4  ModelUsage
      field 9  generation info -> field 4 = google.protobuf.Timestamp
      field 17 retry info -> field 2 = ModelUsage
      field 19 internal model id (string)
      field 21 display label (string)

    ModelUsage
      field 1  model id          field 6  provider
      field 2  input tokens      field 7  message id
      field 3  total output      field 9  reasoning tokens
      field 4  cache write       field 10 visible output tokens
      field 5  cache read        field 11 response id
                                 field 12 provider message id
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..proto import (
    get_all_bytes,
    get_bytes,
    get_text,
    get_varint,
    parse_fields,
    string_candidates,
    timestamp_ms,
)
from ..util import clean_title, file_uri_to_path, ro_uri
from .base import Event, Instance, basename

SOURCE = "antigravity"
SOURCE_LABEL = "Antigravity"

MODEL_IDS: dict[int, str] = {
    246: "gemini-2.5-pro",
    312: "gemini-2.5-flash",
    313: "gemini-2.5-flash-thinking",
    329: "gemini-2.5-flash-thinking",
    330: "gemini-2.5-flash-lite",
    281: "claude-4-sonnet",
    282: "claude-4-sonnet",
    290: "claude-4-opus",
    291: "claude-4-opus",
    333: "claude-4.5-sonnet",
    334: "claude-4.5-sonnet",
    340: "claude-4.5-haiku",
    341: "claude-4.5-haiku",
    342: "gpt-oss-120b",
    1050: "gemini-3.1-flash-lite",
    1071: "gemini-3.6-flash-high",
    1072: "gemini-3.6-flash-medium",
    1073: "gemini-3.6-flash-low",
    1298: "gemini-3.7-flash-high",
    1299: "gemini-3.7-flash-medium",
    1300: "gemini-3.7-flash-low",
    1318: "gemini-3.8-flash-high",
    1319: "gemini-3.8-flash-medium",
    1320: "gemini-3.8-flash-low",
    1417: "gemini-4-argon",
    1418: "gemini-4-argon",
    1419: "gemini-4-argon",
}

LABEL_MODELS = {
    "gemini 3.8 flash (high)": "gemini-3.8-flash-high",
    "gemini 3.8 flash (medium)": "gemini-3.8-flash-medium",
    "gemini 3.8 flash (low)": "gemini-3.8-flash-low",
    "gemini 3.7 flash (high)": "gemini-3.7-flash-high",
    "gemini 3.7 flash (medium)": "gemini-3.7-flash-medium",
    "gemini 3.7 flash (low)": "gemini-3.7-flash-low",
    "gemini 3.6 flash (high)": "gemini-3.6-flash-high",
    "gemini 3.6 flash (medium)": "gemini-3.6-flash-medium",
    "gemini 3.6 flash (low)": "gemini-3.6-flash-low",
    "gemini 3.8 flash": "gemini-3.8-flash",
    "gemini 3.7 flash": "gemini-3.7-flash",
    "gemini 3.6 flash": "gemini-3.6-flash",
    "gemini 3.7 pro": "gemini-3.7-pro",
    "gemini 3.6 pro": "gemini-3.6-pro",
    "gemini 3 pro": "gemini-3-pro",
    "gemini 3.1 pro": "gemini-3.1-pro",
    "gemini 2.5 pro": "gemini-2.5-pro",
    "gemini 2.5 flash": "gemini-2.5-flash",
    "gemini 2.0 flash": "gemini-2.0-flash",
    "gemini 1.5 pro": "gemini-1.5-pro",
    "gemini 1.5 flash": "gemini-1.5-flash",
    "claude 3.7 sonnet": "claude-3-7-sonnet",
    "claude 3.5 sonnet": "claude-3-5-sonnet",
    "claude 3.5 haiku": "claude-3-5-haiku",
    "claude 3 opus": "claude-3-opus",
}

PLACEHOLDERS = {
    "model_placeholder_m318": "gemini-3.8-flash-high",
    "model_placeholder_m319": "gemini-3.8-flash-medium",
    "model_placeholder_m320": "gemini-3.8-flash-low",
    "model_placeholder_m298": "gemini-3.7-flash-high",
    "model_placeholder_m299": "gemini-3.7-flash-medium",
    "model_placeholder_m300": "gemini-3.7-flash-low",
    "model_placeholder_m71": "gemini-3.6-flash-high",
    "model_placeholder_m72": "gemini-3.6-flash-medium",
    "model_placeholder_m73": "gemini-3.6-flash-low",
    "model_placeholder_m417": "gemini-4-argon",
    "model_placeholder_m418": "gemini-4-argon",
    "model_placeholder_m419": "gemini-4-argon",
    "model_placeholder_m50": "gemini-3.1-flash-lite",
    "model_placeholder_m26": "claude-opus-4-6",
    "model_placeholder_m35": "claude-sonnet-4-6",
    "model_placeholder_m36": "gemini-3.1-pro",
    "model_placeholder_m37": "gemini-3.1-pro",
    "model_placeholder_m16": "gemini-3.1-pro",
    "model_placeholder_m18": "gemini-3-flash-preview",
    "model_placeholder_m84": "gemini-3-flash-preview",
    "model_placeholder_m47": "gemini-3-flash-preview",
    "model_placeholder_m132": "gemini-3.5-flash-high",
    "model_placeholder_m133": "gemini-3.5-flash-high",
    "model_placeholder_m187": "gemini-3.5-flash-extra-low",
    "model_placeholder_m20": "gemini-3.5-flash-medium",
    "model_openai_gpt_oss_120b_medium": "gpt-oss-120b",
    "gemini-pro-default": "gemini-3.1-pro",
    "gemini-pro-agent": "gemini-3.1-pro",
    "gemini-3-flash-agent": "gemini-3.5-flash-high",
    "gemini-3-flash-agent-a": "gemini-3.5-flash-high",
    "gemini-3-flash-agent-b": "gemini-3.5-flash-high",
    "gemini-3-flash-a": "gemini-3.5-flash-high",
    "gemini-3-flash-b": "gemini-3.5-flash-high",
    "gemini-3-flash-c": "gemini-3-flash-preview",
    "gemini-3.5-flash-low": "gemini-3.5-flash-medium",
    "gemini-3.1-pro-high": "gemini-3.1-pro",
    "gemini-3.1-pro-low": "gemini-3.1-pro",
    "gemini-3-pro-high": "gemini-3-pro",
    "gemini-3-pro-low": "gemini-3-pro",
}

SURFACES = {
    "antigravity": ("Antigravity", "App"),
    "antigravity-ide": ("Antigravity IDE", "IDE"),
    "antigravity-cli": ("Antigravity CLI", "CLI"),
}


@dataclass
class Usage:
    input: int = 0
    total_output: int = 0
    cache_write: int = 0
    cache_read: int = 0
    reasoning: int = 0
    visible_output: int = 0
    model_id: int | None = None
    provider: int | None = None
    message_id: str | None = None
    response_id: str | None = None
    provider_message_id: str | None = None
    model_text: str | None = None
    label: str | None = None
    ts: int | None = None
    identity: str = ""

    def token_bearing(self) -> bool:
        return (
            self.input
            + self.total_output
            + self.cache_write
            + self.cache_read
            + self.reasoning
            + self.visible_output
        ) > 0


def base_dirs() -> list[Path]:
    dirs = [Path.home() / ".gemini" / "antigravity"]
    dirs.append(Path.home() / ".gemini" / "antigravity-ide")
    dirs.append(Path.home() / ".gemini" / "antigravity-cli")
    cli_home = os.environ.get("GEMINI_CLI_HOME")
    if cli_home:
        dirs.append(Path(cli_home) / "antigravity-cli")
    return dirs


def discover(extra: list[Path]) -> list[Instance]:
    instances: list[Instance] = []
    seen: set[str] = set()
    candidates: list[Path] = []
    for base in base_dirs():
        candidates.append(base / "conversations")
    for path in extra:
        if path.is_file():
            candidates.append(path.parent)
        elif path.name == "conversations" or path.is_dir():
            candidates.append(path)
    for directory in candidates:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.db")):
            if path.name.endswith("-wal") or path.name.endswith("-shm"):
                continue
            key = str(path.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            surface_key = directory.parent.name.lower()
            label, surface = SURFACES.get(surface_key, ("Antigravity", "Conversation"))
            instances.append(
                Instance(
                    source=SOURCE,
                    source_label=label,
                    surface=surface,
                    account_key=surface_key,
                    path=str(path),
                    detail="Antigravity conversation",
                )
            )
    return instances


def _parse_usage(blob: bytes, *, ts: int | None, model_text: str | None, label: str | None,
                 stub: str) -> Usage | None:
    fields = parse_fields(blob)
    if not fields:
        return None
    usage = Usage(
        model_id=get_varint(fields, 1),
        input=int(get_varint(fields, 2) or 0),
        total_output=int(get_varint(fields, 3) or 0),
        cache_write=int(get_varint(fields, 4) or 0),
        cache_read=int(get_varint(fields, 5) or 0),
        provider=get_varint(fields, 6),
        message_id=get_text(fields, 7),
        reasoning=int(get_varint(fields, 9) or 0),
        visible_output=int(get_varint(fields, 10) or 0),
        response_id=get_text(fields, 11),
        provider_message_id=get_text(fields, 12),
        model_text=model_text,
        label=label,
        ts=ts,
    )
    if usage.response_id:
        usage.identity = f"response:{usage.response_id}"
    elif usage.provider_message_id:
        usage.identity = f"provider:{usage.provider_message_id}"
    elif usage.message_id:
        usage.identity = f"message:{usage.message_id}"
    else:
        usage.identity = stub
    return usage


def _parse_generator(blob: bytes, idx: int) -> list[Usage]:
    root = parse_fields(blob)
    chat_model = get_bytes(root, 1)
    if not chat_model:
        return []
    fields = parse_fields(chat_model)
    label = get_text(fields, 21)
    model_text = get_text(fields, 19) or label
    model_id = get_varint(fields, 3)
    ts = None
    generation_info = get_bytes(fields, 9)
    if generation_info:
        ts = timestamp_ms(get_bytes(parse_fields(generation_info), 4))

    usages: list[Usage] = []
    primary_blob = get_bytes(fields, 4)
    if primary_blob:
        usage = _parse_usage(
            primary_blob,
            ts=ts,
            model_text=model_text,
            label=label,
            stub=f"gen:{idx}:0",
        )
        if usage:
            if usage.model_id is None:
                usage.model_id = model_id
            usages.append(usage)

    for retry_index, retry_blob in enumerate(get_all_bytes(fields, 17)):
        retry_fields = parse_fields(retry_blob)
        usage_blob = get_bytes(retry_fields, 2)
        if not usage_blob:
            continue
        usage = _parse_usage(
            usage_blob,
            ts=ts,
            model_text=model_text,
            label=label,
            stub=f"gen:{idx}:retry:{retry_index}",
        )
        if usage:
            if usage.model_id is None:
                usage.model_id = model_id
            usages.append(usage)
    return usages


def _parse_step(blob: bytes, idx: int) -> list[Usage]:
    fields = parse_fields(blob)
    ts = timestamp_ms(get_bytes(fields, 8)) or timestamp_ms(get_bytes(fields, 1))
    model_info = get_bytes(fields, 24)
    model_text = None
    model_id = None
    provider = None
    if model_info:
        info = parse_fields(model_info)
        model_text = get_text(info, 12) or get_text(info, 8)
        model_id = get_varint(info, 1)
        provider = get_varint(info, 7)

    usages: list[Usage] = []
    primary_blob = get_bytes(fields, 9)
    if primary_blob:
        usage = _parse_usage(primary_blob, ts=ts, model_text=model_text, label=None, stub=f"step:{idx}:0")
        if usage:
            usage.model_id = usage.model_id or model_id
            usage.provider = usage.provider or provider
            usages.append(usage)
    for retry_index, retry_blob in enumerate(get_all_bytes(fields, 28)):
        retry_fields = parse_fields(retry_blob)
        usage_blob = get_bytes(retry_fields, 2)
        if not usage_blob:
            continue
        usage = _parse_usage(
            usage_blob,
            ts=ts,
            model_text=model_text,
            label=None,
            stub=f"step:{idx}:retry:{retry_index}",
        )
        if usage:
            usage.model_id = usage.model_id or model_id
            usage.provider = usage.provider or provider
            usages.append(usage)
    return usages


def _normalize_model(model_id: int | None, text: str | None, label: str | None) -> str | None:
    if model_id is not None:
        if model_id in MODEL_IDS:
            return MODEL_IDS[model_id]
        if model_id >= 1000:
            placeholder = PLACEHOLDERS.get(f"model_placeholder_m{model_id - 1000}")
            if placeholder:
                return placeholder
    raw = (text or label or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower in PLACEHOLDERS:
        return PLACEHOLDERS[lower]
    if lower in LABEL_MODELS:
        return LABEL_MODELS[lower]
    base = lower.split("(")[0].strip()
    if base in LABEL_MODELS:
        return LABEL_MODELS[base]
    converted = base.replace(" ", "-")
    if converted.startswith(("gemini-", "claude-", "gpt-", "model_")):
        return converted
    return raw


def _display_label(model_id: int | None, text: str | None, label: str | None, model: str | None) -> str | None:
    if label:
        return label
    if model:
        return model.replace("-", " ").title()
    return None


def _trajectory(conn: sqlite3.Connection) -> tuple[str | None, int | None]:
    try:
        row = conn.execute("select data from trajectory_metadata_blob order by rowid limit 1").fetchone()
    except Exception:
        return None, None
    if not row or not row[0]:
        return None, None
    fields = parse_fields(row[0])
    path_text = get_text(fields, 7) or get_text(fields, 1)
    project = file_uri_to_path(path_text)
    ts = timestamp_ms(get_bytes(fields, 2))
    return project, ts


def _session_title(conn: sqlite3.Connection, project: str | None, session_id: str) -> str:
    try:
        rows = conn.execute(
            "select step_payload from steps where step_type = 14 order by idx limit 4"
        ).fetchall()
    except Exception:
        rows = []
    best = None
    for row in rows:
        if not row[0]:
            continue
        for candidate in string_candidates(row[0], min_length=6):
            title = clean_title(candidate)
            if title:
                best = title
                break
        if best:
            break
    if best:
        return best
    project_name = basename(project)
    if project_name:
        return project_name
    return f"Conversation {session_id[:8]}"


def _merge(usages: list[Usage]) -> list[Usage]:
    merged: dict[str, Usage] = {}
    for usage in usages:
        if not usage.token_bearing():
            continue
        existing = merged.get(usage.identity)
        if not existing:
            merged[usage.identity] = usage
            continue
        existing.input = max(existing.input, usage.input)
        existing.total_output = max(existing.total_output, usage.total_output)
        existing.cache_write = max(existing.cache_write, usage.cache_write)
        existing.cache_read = max(existing.cache_read, usage.cache_read)
        existing.reasoning = max(existing.reasoning, usage.reasoning)
        existing.visible_output = max(existing.visible_output, usage.visible_output)
        existing.ts = existing.ts or usage.ts
        existing.model_id = existing.model_id or usage.model_id
        existing.model_text = existing.model_text or usage.model_text
        existing.label = existing.label or usage.label
        existing.provider = existing.provider or usage.provider
    return list(merged.values())


def scan(instance: Instance) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    try:
        conn = sqlite3.connect(ro_uri(instance.path), uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
    except Exception as exc:
        return [], [f"{instance.path}: {exc}"]

    try:
        tables = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type='table'")
        }
        if "gen_metadata" not in tables:
            return [], errors
        project, trajectory_ts = _trajectory(conn)
        session_id = Path(instance.path).stem
        mtime = int(Path(instance.path).stat().st_mtime * 1000)
        fallback_ts = trajectory_ts or mtime
        title = _session_title(conn, project, session_id)

        usages: list[Usage] = []
        for row in conn.execute("select idx, data from gen_metadata order by idx"):
            if not row["data"]:
                continue
            usages.extend(_parse_generator(bytes(row["data"]), int(row["idx"])))
        if "steps" in tables:
            for row in conn.execute("select idx, metadata from steps where metadata is not null order by idx"):
                if not row["metadata"]:
                    continue
                usages.extend(_parse_step(bytes(row["metadata"]), int(row["idx"])))

        for usage in _merge(usages):
            total_output = max(usage.total_output, usage.visible_output + usage.reasoning)
            output = max(usage.visible_output, total_output - usage.reasoning)
            reasoning = max(usage.reasoning, total_output - output)
            model = _normalize_model(usage.model_id, usage.model_text, usage.label)
            label = _display_label(usage.model_id, usage.model_text, usage.label, model)
            events.append(
                Event(
                    source=SOURCE,
                    source_label=instance.source_label,
                    surface=instance.surface,
                    account_key=instance.account_key,
                    session_id=session_id,
                    native_id=usage.identity,
                    ts=usage.ts or fallback_ts,
                    model=model,
                    model_label=label,
                    session_title=title,
                    project=basename(project),
                    input=usage.input,
                    output=output,
                    reasoning=reasoning,
                    cache_read=usage.cache_read,
                    cache_write=usage.cache_write,
                    cost=None,
                    cost_kind="estimated",
                    price_provider="google",
                    ref=instance.path,
                )
            )
    except Exception as exc:
        errors.append(f"{instance.path}: {exc}")
    finally:
        conn.close()
    return events, errors
