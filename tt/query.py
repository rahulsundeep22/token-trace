"""Aggregation queries that power both the dashboard and the CLI report."""

from __future__ import annotations

import datetime as dt
import time
from collections import defaultdict

from .config import account_label, db_path as default_db_path
from .db import get_meta
from .util import local_date, local_midnight


def _bounds(days: int) -> tuple[dt.datetime | None, dt.datetime | None, dt.datetime, dt.datetime | None]:
    end = dt.datetime.now().astimezone()
    if days and days > 0:
        start = local_midnight(days - 1)
        prev_start = start - dt.timedelta(days=days)
        return start, prev_start, end, start
    return None, None, end, None


def _where(days: int, source: str | None, account: str | None, model: str | None):
    clauses = []
    params: list = []
    start, prev_start, end, prev_end = _bounds(days)
    if start:
        clauses.append("ts >= ?")
        params.append(int(start.timestamp() * 1000))
    if start:
        clauses.append("ts < ?")
        params.append(int(end.timestamp() * 1000) + 1)
    if source:
        clauses.append("source_label = ?")
        params.append(source)
    if account:
        clauses.append("account_key = ?")
        params.append(account)
    if model:
        clauses.append("model = ?")
        params.append(model)
    sql = " and ".join(clauses)
    return (f"where {sql}" if sql else ""), params, start, prev_start, end, prev_end


def _blank() -> dict:
    return {
        "tokens": 0,
        "input": 0,
        "output": 0,
        "reasoning": 0,
        "cache_read": 0,
        "cache_write": 0,
        "cost": 0.0,
        "cost_exact": 0.0,
        "cost_estimated": 0.0,
        "unknown_cost_events": 0,
        "events": 0,
        "sessions": set(),
    }


def _add(agg: dict, row) -> None:
    inp = row["input"] or 0
    out = row["output"] or 0
    reason = row["reasoning"] or 0
    cache_read = row["cache_read"] or 0
    cache_write = row["cache_write"] or 0
    agg["input"] += inp
    agg["output"] += out
    agg["reasoning"] += reason
    agg["cache_read"] += cache_read
    agg["cache_write"] += cache_write
    agg["tokens"] += inp + out + reason + cache_read + cache_write
    agg["events"] += 1
    agg["sessions"].add((row["source"], row["account_key"], row["session_id"]))
    if row["cost"] is None:
        agg["unknown_cost_events"] += 1
    else:
        agg["cost"] += float(row["cost"])
        if row["cost_kind"] == "exact":
            agg["cost_exact"] += float(row["cost"])
        else:
            agg["cost_estimated"] += float(row["cost"])


def _pct(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _finish(agg: dict) -> dict:
    return {
        "tokens": agg["tokens"],
        "input": agg["input"],
        "output": agg["output"],
        "reasoning": agg["reasoning"],
        "cache_read": agg["cache_read"],
        "cache_write": agg["cache_write"],
        "cost": round(agg["cost"], 6),
        "cost_exact": round(agg["cost_exact"], 6),
        "cost_estimated": round(agg["cost_estimated"], 6),
        "unknown_cost_events": agg["unknown_cost_events"],
        "events": agg["events"],
        "sessions": len(agg["sessions"]),
    }


def summary(
    conn,
    *,
    days: int = 30,
    source: str | None = None,
    account: str | None = None,
    model: str | None = None,
    config: dict | None = None,
    limit_sessions: int = 60,
) -> dict:
    config = config or {}
    where, params, start, prev_start, end, prev_end = _where(days, source, account, model)
    rows = conn.execute(f"select * from events {where} order by ts", params).fetchall()

    totals = _blank()
    daily: dict[str, dict] = defaultdict(lambda: {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0, "tokens": 0, "cost": 0.0, "events": 0})
    by_source: dict[str, dict] = defaultdict(_blank)
    by_account: dict[str, dict] = defaultdict(_blank)
    by_model: dict[str, dict] = defaultdict(_blank)
    sessions: dict[tuple, dict] = {}

    for row in rows:
        _add(totals, row)
        day = local_date(row["ts"])
        bucket = daily[day]
        bucket["input"] += row["input"] or 0
        bucket["output"] += row["output"] or 0
        bucket["reasoning"] += row["reasoning"] or 0
        bucket["cache_read"] += row["cache_read"] or 0
        bucket["cache_write"] += row["cache_write"] or 0
        bucket["tokens"] += (row["input"] or 0) + (row["output"] or 0) + (row["reasoning"] or 0) + (row["cache_read"] or 0) + (row["cache_write"] or 0)
        bucket["cost"] += float(row["cost"] or 0)
        bucket["events"] += 1
        _add(by_source[row["source_label"]], row)
        _add(by_account[row["account_key"]], row)
        model_key = row["model"] or "unknown"
        model_agg = by_model[model_key]
        _add(model_agg, row)
        if not model_agg.get("label") and row["model_label"]:
            model_agg["label"] = row["model_label"]
        model_agg.setdefault("providers", set()).add(row["price_provider"] or row["source"])

        key = (row["source"], row["account_key"], row["session_id"])
        session = sessions.get(key)
        if session is None:
            session = {
                "source": row["source"],
                "source_label": row["source_label"],
                "surface": row["surface"],
                "account_key": row["account_key"],
                "account": account_label(config, row["account_key"]),
                "id": row["session_id"],
                "title": row["session_title"],
                "project": row["project"],
                "models": defaultdict(int),
                "model_labels": {},
                "tokens": 0,
                "input": 0,
                "output": 0,
                "reasoning": 0,
                "cache_read": 0,
                "cache_write": 0,
                "cost": 0.0,
                "unknown_cost": 0,
                "events": 0,
                "start": row["ts"],
                "end": row["ts"],
            }
            sessions[key] = session
        session["start"] = min(session["start"], row["ts"])
        session["end"] = max(session["end"], row["ts"])
        session["tokens"] += (row["input"] or 0) + (row["output"] or 0) + (row["reasoning"] or 0) + (row["cache_read"] or 0) + (row["cache_write"] or 0)
        session["input"] += row["input"] or 0
        session["output"] += row["output"] or 0
        session["reasoning"] += row["reasoning"] or 0
        session["cache_read"] += row["cache_read"] or 0
        session["cache_write"] += row["cache_write"] or 0
        if row["cost"] is not None:
            session["cost"] += float(row["cost"])
        else:
            session["unknown_cost"] += 1
        session["events"] += 1
        if row["session_title"]:
            session["title"] = row["session_title"]
        if row["project"]:
            session["project"] = row["project"]
        model_name = row["model"] or "unknown"
        session["models"][model_name] += (row["input"] or 0) + (row["output"] or 0) + (row["reasoning"] or 0) + (row["cache_read"] or 0) + (row["cache_write"] or 0)
        if row["model_label"]:
            session["model_labels"][model_name] = row["model_label"]

    # Previous period for deltas (all-time has no previous window).
    prev_totals = None
    if prev_start and prev_end:
        prev_rows = conn.execute(
            "select * from events where ts >= ? and ts < ?"
            + (" and source_label = ?" if source else "")
            + (" and account_key = ?" if account else "")
            + (" and model = ?" if model else "")
            + " order by ts",
            [int(prev_start.timestamp() * 1000), int(prev_end.timestamp() * 1000)]
            + ([source] if source else [])
            + ([account] if account else [])
            + ([model] if model else []),
        ).fetchall()
        prev_agg = _blank()
        for row in prev_rows:
            _add(prev_agg, row)
        prev_totals = _finish(prev_agg)

    total_tokens = totals["tokens"] or 1
    sources = []
    for label, agg in by_source.items():
        finished = _finish(agg)
        finished["label"] = label
        finished["share"] = round(finished["tokens"] / total_tokens * 100, 1)
        sources.append(finished)
    sources.sort(key=lambda item: item["tokens"], reverse=True)

    accounts = []
    for key, agg in by_account.items():
        finished = _finish(agg)
        finished["key"] = key
        finished["label"] = account_label(config, key)
        finished["share"] = round(finished["tokens"] / total_tokens * 100, 1)
        accounts.append(finished)
    accounts.sort(key=lambda item: item["tokens"], reverse=True)

    models = []
    for key, agg in by_model.items():
        finished = _finish(agg)
        finished["model"] = key
        finished["label"] = agg.get("label") or key
        finished["providers"] = sorted(agg.get("providers") or [])
        finished["share"] = round(finished["tokens"] / total_tokens * 100, 1)
        models.append(finished)
    models.sort(key=lambda item: item["tokens"], reverse=True)

    session_list = []
    for session in sessions.values():
        items = sorted(session["models"].items(), key=lambda pair: pair[1], reverse=True)
        session_list.append(
            {
                "source": session["source"],
                "source_label": session["source_label"],
                "surface": session["surface"],
                "account_key": session["account_key"],
                "account": session["account"],
                "id": session["id"],
                "title": session["title"] or f"Session {session['id'][:8]}",
                "project": session["project"],
                "tokens": session["tokens"],
                "input": session["input"],
                "output": session["output"],
                "reasoning": session["reasoning"],
                "cache_read": session["cache_read"],
                "cache_write": session["cache_write"],
                "cost": round(session["cost"], 6),
                "unknown_cost": session["unknown_cost"] > 0,
                "events": session["events"],
                "start": session["start"],
                "end": session["end"],
                "models": [
                    {"model": name, "label": session["model_labels"].get(name) or name, "tokens": tokens}
                    for name, tokens in items[:4]
                ],
            }
        )
    session_list.sort(key=lambda item: item["end"], reverse=True)

    # Fill the daily series so quiet days still appear on the chart.
    daily_list = []
    if start:
        cursor = start.date()
        last = end.date()
        while cursor <= last:
            key = cursor.isoformat()
            bucket = daily.get(key) or {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0, "tokens": 0, "cost": 0.0, "events": 0}
            bucket = dict(bucket)
            bucket["date"] = key
            daily_list.append(bucket)
            cursor += dt.timedelta(days=1)
    else:
        for key in sorted(daily):
            bucket = dict(daily[key])
            bucket["date"] = key
            daily_list.append(bucket)

    totals_finished = _finish(totals)
    if prev_totals:
        totals_finished["prev_tokens"] = prev_totals["tokens"]
        totals_finished["prev_cost"] = prev_totals["cost"]
        totals_finished["token_delta_pct"] = _pct(totals_finished["tokens"], prev_totals["tokens"])
        totals_finished["cost_delta_pct"] = _pct(totals_finished["cost"], prev_totals["cost"])
    else:
        totals_finished["prev_tokens"] = None
        totals_finished["prev_cost"] = None
        totals_finished["token_delta_pct"] = None
        totals_finished["cost_delta_pct"] = None

    options = _options(conn, config)
    last_scan = get_meta(conn, "last_scan")
    return {
        "range": {
            "days": days,
            "start": start.date().isoformat() if start else None,
            "end": end.date().isoformat(),
        },
        "totals": totals_finished,
        "daily": daily_list,
        "sources": sources,
        "accounts": accounts,
        "models": models,
        "sessions": session_list[:limit_sessions],
        "options": options,
        "meta": {
            "db": str(default_db_path()),
            "last_scan": int(last_scan) if last_scan else None,
            "generated_at": int(time.time() * 1000),
            "total_events": conn.execute("select count(*) from events").fetchone()[0],
        },
    }


def _options(conn, config: dict) -> dict:
    sources = [
        row[0]
        for row in conn.execute("select distinct source_label from events order by source_label")
    ]
    accounts = []
    for row in conn.execute(
        "select account_key, count(*) as n from events group by account_key order by n desc"
    ):
        accounts.append({"key": row[0], "label": account_label(config, row[0])})
    models = []
    for row in conn.execute(
        """
        select model, max(model_label), count(*) as n
        from events where model is not null
        group by model order by n desc
        """
    ):
        models.append({"model": row[0], "label": row[1] or row[0]})
    return {"sources": sources, "accounts": accounts, "models": models}


def totals_for_terminal(conn, config: dict, days: int) -> dict:
    return summary(conn, days=days, config=config, limit_sessions=12)
