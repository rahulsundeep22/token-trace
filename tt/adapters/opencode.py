"""OpenCode adapter.

OpenCode 2 stores one row per message in `session_message` and rolls session
metadata into `session_v2`. Assistant messages carry an exact token breakdown
and, for hosted gateways, an exact per-message cost.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ..pricing import load_local_catalog
from ..util import ro_uri
from .base import Event, Instance, basename

SOURCE = "opencode"
SOURCE_LABEL = "OpenCode"


def data_dirs(extra: list[Path]) -> list[Path]:
    dirs: list[Path] = []
    env_dir = os.environ.get("OPENCODE_DATA_DIR")
    if env_dir:
        dirs.append(Path(env_dir))
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        dirs.append(Path(xdg) / "opencode")
    dirs.append(Path.home() / ".local" / "share" / "opencode")
    dirs.extend(extra)
    seen: set[str] = set()
    return [d for d in dirs if not (str(d).lower() in seen or seen.add(str(d).lower()))]


def discover(extra: list[Path]) -> list[Instance]:
    instances: list[Instance] = []
    for directory in data_dirs(extra):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("opencode*.db")):
            if path.name.endswith("-shm") or path.name.endswith("-wal"):
                continue
            surface = "Preview" if "next" in path.stem else "CLI"
            instances.append(
                Instance(
                    source=SOURCE,
                    source_label=SOURCE_LABEL,
                    surface=surface,
                    account_key=SOURCE if surface == "CLI" else "opencode-preview",
                    path=str(path),
                    detail="OpenCode database",
                )
            )
    return instances


def _catalog_names() -> dict[tuple[str, str], str]:
    catalog = load_local_catalog()
    names: dict[tuple[str, str], str] = {}
    for provider, models in catalog.items():
        for model_id, entry in models.items():
            name = entry.get("name")
            if name:
                names[(provider, model_id)] = name
    return names


def _tokens_from(data: dict) -> tuple[int, int, int, int, int]:
    tokens = data.get("tokens") or {}
    cache = tokens.get("cache") or {}
    return (
        int(tokens.get("input") or 0),
        int(tokens.get("output") or 0),
        int(tokens.get("reasoning") or 0),
        int(cache.get("read") or 0),
        int(cache.get("write") or 0),
    )


def _model_from(data: dict) -> tuple[str | None, str | None]:
    model = data.get("model") or {}
    model_id = model.get("id") or model.get("modelID")
    provider = model.get("providerID")
    return model_id, provider


def scan(instance: Instance) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    names = _catalog_names()
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
        if "session_message" in tables:
            events, errors = _scan_v2(conn, instance, names)
        elif "message" in tables:
            events, errors = _scan_v1(conn, instance, names)
    except Exception as exc:
        errors.append(f"{instance.path}: {exc}")
    finally:
        conn.close()

    # Deduplicate by message id in case a database was copied between channels.
    unique: dict[str, Event] = {}
    for event in events:
        unique[event.native_id] = event
    return list(unique.values()), errors


def _scan_v2(
    conn: sqlite3.Connection,
    instance: Instance,
    names: dict[tuple[str, str], str],
) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    has_sessions = conn.execute(
        "select 1 from sqlite_master where type='table' and name='session_v2'"
    ).fetchone()
    if has_sessions:
        query = """
            select m.id, m.session_id, m.data, m.time_created,
                   s.title, s.directory, s.path
            from session_message m
            left join session_v2 s on s.id = m.session_id
            where m.type = 'assistant'
        """
    else:
        query = """
            select id, session_id, data, time_created, null, null, null
            from session_message where type = 'assistant'
        """
    try:
        rows = conn.execute(query).fetchall()
    except Exception as exc:
        return [], [f"{instance.path}: {exc}"]

    for row in rows:
        try:
            data = json.loads(row["data"])
        except Exception:
            continue
        input_tokens, output_tokens, reasoning, cache_read, cache_write = _tokens_from(data)
        if input_tokens + output_tokens + reasoning + cache_read + cache_write <= 0:
            continue
        model, provider = _model_from(data)
        when = data.get("time") or {}
        ts = (
            when.get("completed")
            or when.get("created")
            or row["time_created"]
            or 0
        )
        cost = data.get("cost")
        cost_kind = "exact" if cost is not None else "estimated"
        label = names.get((provider or "", model or ""))
        events.append(
            Event(
                source=SOURCE,
                source_label=SOURCE_LABEL,
                surface=instance.surface,
                account_key=instance.account_key,
                session_id=row["session_id"],
                native_id=row["id"],
                ts=int(ts or 0),
                model=model,
                model_label=label,
                session_title=row["title"] or None,
                project=basename(row["directory"] or row["path"]),
                input=input_tokens,
                output=output_tokens,
                reasoning=reasoning,
                cache_read=cache_read,
                cache_write=cache_write,
                cost=float(cost) if cost is not None else None,
                cost_kind=cost_kind,
                price_provider="opencode",
                ref=instance.path,
            )
        )
    return events, errors


def _scan_v1(
    conn: sqlite3.Connection,
    instance: Instance,
    names: dict[tuple[str, str], str],
) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    try:
        rows = conn.execute("select id, session_id, data from message").fetchall()
    except Exception as exc:
        return [], [f"{instance.path}: {exc}"]
    for row in rows:
        try:
            data = json.loads(row["data"])
        except Exception:
            continue
        if data.get("role") != "assistant":
            continue
        input_tokens, output_tokens, reasoning, cache_read, cache_write = _tokens_from(data)
        if input_tokens + output_tokens + reasoning + cache_read + cache_write <= 0:
            continue
        model, provider = _model_from(data)
        when = data.get("time") or {}
        cost = data.get("cost")
        events.append(
            Event(
                source=SOURCE,
                source_label=SOURCE_LABEL,
                surface=instance.surface,
                account_key=instance.account_key,
                session_id=row["session_id"] or "",
                native_id=row["id"],
                ts=int(when.get("completed") or when.get("created") or 0),
                model=model,
                model_label=names.get((provider or "", model or "")),
                project=None,
                input=input_tokens,
                output=output_tokens,
                reasoning=reasoning,
                cache_read=cache_read,
                cache_write=cache_write,
                cost=float(cost) if cost is not None else None,
                cost_kind="exact" if cost is not None else "estimated",
                price_provider="opencode",
                ref=instance.path,
            )
        )
    return events, errors
