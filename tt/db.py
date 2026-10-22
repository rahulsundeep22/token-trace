"""SQLite storage for normalized usage events."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .adapters.base import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_label TEXT NOT NULL,
    surface TEXT NOT NULL,
    account_key TEXT NOT NULL,
    session_id TEXT NOT NULL,
    session_title TEXT,
    project TEXT,
    model TEXT,
    model_label TEXT,
    ts INTEGER NOT NULL,
    input INTEGER NOT NULL DEFAULT 0,
    output INTEGER NOT NULL DEFAULT 0,
    reasoning INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0,
    cost REAL,
    cost_kind TEXT NOT NULL DEFAULT 'estimated',
    price_provider TEXT,
    ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(source, account_key, session_id);
CREATE TABLE IF NOT EXISTS scans (
    source TEXT NOT NULL,
    account_key TEXT NOT NULL,
    path TEXT NOT NULL,
    scanned_at INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (source, account_key, path)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_events(conn: sqlite3.Connection, events: list[Event]) -> int:
    if not events:
        return 0
    now = int(time.time() * 1000)
    rows = [
        (
            event_id(event),
            event.source,
            event.source_label,
            event.surface,
            event.account_key,
            event.session_id,
            event.session_title,
            event.project,
            event.model,
            event.model_label,
            event.ts,
            event.input,
            event.output,
            event.reasoning,
            event.cache_read,
            event.cache_write,
            event.cost,
            event.cost_kind,
            event.price_provider,
            event.ref,
        )
        for event in events
    ]
    conn.executemany(
        """
        INSERT INTO events (
            id, source, source_label, surface, account_key, session_id,
            session_title, project, model, model_label, ts, input, output,
            reasoning, cache_read, cache_write, cost, cost_kind, price_provider, ref
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            source_label = excluded.source_label,
            surface = excluded.surface,
            session_title = COALESCE(excluded.session_title, events.session_title),
            project = COALESCE(excluded.project, events.project),
            model = COALESCE(excluded.model, events.model),
            model_label = COALESCE(excluded.model_label, events.model_label),
            ts = excluded.ts,
            input = excluded.input,
            output = excluded.output,
            reasoning = excluded.reasoning,
            cache_read = excluded.cache_read,
            cache_write = excluded.cache_write,
            cost = excluded.cost,
            cost_kind = excluded.cost_kind,
            price_provider = excluded.price_provider,
            ref = excluded.ref
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def event_id(event: Event) -> str:
    import hashlib

    raw = "|".join(
        [
            event.source,
            event.account_key,
            event.session_id,
            event.native_id,
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def record_scan(
    conn: sqlite3.Connection,
    source: str,
    account_key: str,
    path: str,
    event_count: int,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO scans (source, account_key, path, scanned_at, event_count, error)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, account_key, path) DO UPDATE SET
            scanned_at = excluded.scanned_at,
            event_count = excluded.event_count,
            error = excluded.error
        """,
        (source, account_key, path, int(time.time() * 1000), event_count, error),
    )
    conn.commit()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("select value from meta where key=?", (key,)).fetchone()
    return row[0] if row else None
