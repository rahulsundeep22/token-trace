"""Scan orchestration: discover sources, normalize, price and persist."""

from __future__ import annotations

import time

from .adapters import ADAPTERS
from .config import db_path as default_db_path
from .config import extra_paths
from .db import connect, record_scan, set_meta, upsert_events
from .pricing import Pricing


def scan_all(config: dict, *, db_path=None, on_progress=None) -> dict:
    started = time.time()
    conn = connect(db_path) if db_path else connect(default_db_path())
    before = conn.execute("select count(*) from events").fetchone()[0]
    pricing = Pricing(config.get("pricing") or {})
    report = {"sources": {}, "errors": [], "instances": 0, "events": 0}
    try:
        for adapter in ADAPTERS:
            source = adapter.SOURCE
            participants = adapter.discover(extra_paths(config, source))
            source_report = {"instances": 0, "events": 0, "errors": []}
            for instance in participants:
                source_report["instances"] += 1
                report["instances"] += 1
                if on_progress:
                    on_progress(f"Scanning {instance.source_label} - {instance.surface}")
                try:
                    events, errors = adapter.scan(instance)
                except Exception as exc:  # defensive: one broken source never blocks the rest
                    events, errors = [], [f"{instance.path}: {exc}"]
                source_report["errors"].extend(errors)
                report["errors"].extend(errors)
                for event in events:
                    if event.cost is None:
                        cost, basis = pricing.estimate(
                            event.model,
                            event.price_provider or event.source,
                            event.input,
                            event.output,
                            event.reasoning,
                            event.cache_read,
                            event.cache_write,
                        )
                        event.cost = cost
                        event.cost_kind = "estimated" if cost is not None else "unknown"
                        if basis:
                            event.price_provider = f"{event.price_provider}:{basis}"
                    elif event.cost_kind == "unknown":
                        event.cost_kind = "exact"
                upsert_events(conn, events)
                record_scan(
                    conn,
                    instance.source,
                    instance.account_key,
                    instance.path,
                    len(events),
                    "; ".join(errors) if errors else None,
                )
                source_report["events"] += len(events)
                report["events"] += len(events)
            report["sources"][source] = source_report
        after = conn.execute("select count(*) from events").fetchone()[0]
        report["new_events"] = after - before
        report["total_events"] = after
        report["duration_ms"] = int((time.time() - started) * 1000)
        report["finished_at"] = int(time.time() * 1000)
        set_meta(conn, "last_scan", str(report["finished_at"]))
    finally:
        conn.close()
    return report
