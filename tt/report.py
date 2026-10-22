"""Terminal reporting and diagnostics."""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

from .adapters import ADAPTERS
from .config import account_label, config_path, db_path as default_db_path, extra_paths, load_config
from .db import connect, get_meta
from .query import summary


def fmt_tokens(value: float) -> str:
    value = float(value or 0)
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{int(value):,}"


def fmt_cost(value: float | None, unknown: int = 0) -> str:
    if value is None or (value == 0 and unknown):
        return "n/a"
    if value == 0:
        return "$0.00"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:.4f}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "no prior"
    return f"{value:+.1f}%"


def table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    aligns = aligns or ["left"] * len(headers)

    def line(cells):
        parts = []
        for index, cell in enumerate(cells):
            text = str(cell)
            if aligns[index] == "right":
                parts.append(text.rjust(widths[index]))
            else:
                parts.append(text.ljust(widths[index]))
        return "  ".join(parts).rstrip()

    output = [line(headers), "  ".join("-" * width for width in widths)]
    output.extend(line(row) for row in rows)
    return "\n".join(output)


def print_scan_report(report: dict) -> None:
    print()
    print(f"  Scan complete in {report.get('duration_ms', 0)} ms")
    print(
        f"  {report.get('instances', 0)} sources | "
        f"{report.get('events', 0)} usage records | "
        f"{report.get('new_events', 0)} new | "
        f"{report.get('total_events', 0)} total in database"
    )
    print()
    for source, info in report.get("sources", {}).items():
        if info["instances"] or info["errors"]:
            print(
                f"    {source:<14} {info['instances']:>3} files  "
                f"{info['events']:>7} records"
            )
        for error in info["errors"][:4]:
            print(f"      ! {error}")
    if report.get("errors"):
        print(f"\n  {len(report['errors'])} warning(s); other sources still scanned.")


def cmd_scan(config: dict) -> int:
    from .scan import scan_all

    report = scan_all(config, on_progress=lambda message: print(f"  {message}..."))
    print_scan_report(report)
    _print_summary(config, days=30)
    return 0


def _print_summary(config: dict, days: int) -> None:
    conn = connect(default_db_path())
    try:
        data = summary(conn, days=days, config=config, limit_sessions=8)
    finally:
        conn.close()
    totals = data["totals"]
    if not totals["events"]:
        print("\n  No usage recorded yet. Run a scan after using an AI app.\n")
        return
    label = "all time" if not days else f"last {days} days"
    print()
    print(f"  TokenTrace - {label}")
    print("  " + "=" * 58)
    print(f"  Total tokens    {fmt_tokens(totals['tokens']):>10}   {fmt_pct(totals['token_delta_pct'])}")
    print(
        f"    input {fmt_tokens(totals['input'])} | "
        f"cache read {fmt_tokens(totals['cache_read'])} | "
        f"output {fmt_tokens(totals['output'])} | "
        f"reasoning {fmt_tokens(totals['reasoning'])}"
    )
    print(
        f"  Est. value      {fmt_cost(totals['cost'], totals['unknown_cost_events']):>10}   "
        f"{fmt_pct(totals['cost_delta_pct'])}   "
        f"({totals['unknown_cost_events']} unpriced records)"
    )
    print(f"  Sessions        {totals['sessions']:>10}")
    print(f"  Events          {totals['events']:>10}")
    print()

    if data["sources"]:
        print("  By app")
        rows = [
            [
                item["label"],
                fmt_tokens(item["tokens"]),
                f"{item['share']:.1f}%",
                fmt_cost(item["cost"], item["unknown_cost_events"]),
                str(item["sessions"]),
            ]
            for item in data["sources"]
        ]
        print(_indent(table(["App", "Tokens", "Share", "Value", "Sessions"], rows, ["left", "right", "right", "right", "right"])))
        print()

    if data["models"]:
        print("  By model")
        rows = [
            [
                item["label"][:34],
                fmt_tokens(item["tokens"]),
                f"{item['share']:.1f}%",
                fmt_cost(item["cost"], item["unknown_cost_events"]),
            ]
            for item in data["models"][:8]
        ]
        print(_indent(table(["Model", "Tokens", "Share", "Value"], rows, ["left", "right", "right", "right"])))
        print()

    if data["sessions"]:
        print("  Recent sessions")
        rows = []
        for item in data["sessions"][:8]:
            when = dt.datetime.fromtimestamp(item["end"] / 1000).astimezone().strftime("%b %d %H:%M")
            rows.append(
                [
                    when,
                    item["source_label"][:18],
                    (item["title"] or "")[:40],
                    fmt_tokens(item["tokens"]),
                    fmt_cost(item["cost"], 1 if item["unknown_cost"] else 0),
                ]
            )
        print(_indent(table(["When", "App", "Session", "Tokens", "Value"], rows, ["left", "left", "left", "right", "right"])))
    print()


def _indent(block: str) -> str:
    return "\n".join("  " + line for line in block.splitlines())


def cmd_report(config: dict, days: int) -> int:
    _print_summary(config, days)
    return 0


def cmd_doctor(config: dict) -> int:
    print("\n  TokenTrace doctor")
    print("  " + "=" * 58)
    print(f"  Data directory   {default_db_path().parent}")
    print(f"  Database         {default_db_path()}")
    print(f"  Config           {config_path()}")
    print(f"  Account labels   {json.dumps(config.get('accounts') or {}, ensure_ascii=False)}")
    print()
    print("  Detected sources")
    found = 0
    for adapter in ADAPTERS:
        instances = adapter.discover(extra_paths(config, adapter.SOURCE))
        found += len(instances)
        status = f"{len(instances)} file(s)" if instances else "not found"
        print(f"    {adapter.SOURCE_LABEL:<18} {status}")
        for instance in instances[:6]:
            print(f"      - {instance.path}")
        if len(instances) > 6:
            print(f"      ... and {len(instances) - 6} more")
    print()
    conn = connect(default_db_path())
    try:
        total = conn.execute("select count(*) from events").fetchone()[0]
        first = conn.execute("select min(ts), max(ts) from events").fetchone()
        last_scan = get_meta(conn, "last_scan")
        print(f"  Stored events    {total:,}")
        if first and first[0]:
            start = dt.datetime.fromtimestamp(first[0] / 1000).astimezone().strftime("%Y-%m-%d")
            end = dt.datetime.fromtimestamp(first[1] / 1000).astimezone().strftime("%Y-%m-%d")
            print(f"  History          {start} -> {end}")
        if last_scan:
            when = dt.datetime.fromtimestamp(int(last_scan) / 1000).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            print(f"  Last scan        {when}")
    finally:
        conn.close()
    if not found:
        print("\n  No supported app data found yet. Use OpenCode or Antigravity, then re-run.")
    print()
    return 0


def cmd_export(config: dict, days: int, out: str, fmt: str) -> int:
    conn = connect(default_db_path())
    try:
        if days:
            start = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=days - 1)
            rows = conn.execute("select * from events where ts >= ? order by ts", (int(start.timestamp() * 1000),)).fetchall()
        else:
            rows = conn.execute("select * from events order by ts").fetchall()
    finally:
        conn.close()

    path = Path(out).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for row in rows:
        record = dict(row)
        record["timestamp"] = dt.datetime.fromtimestamp(row["ts"] / 1000).astimezone().isoformat()
        record["account"] = account_label(config, row["account_key"])
        record["total_tokens"] = row["input"] + row["output"] + row["reasoning"] + row["cache_read"] + row["cache_write"]
        records.append(record)

    if fmt == "json":
        path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        columns = [
            "timestamp", "source", "surface", "account", "session_id", "session_title",
            "project", "model", "model_label", "input", "output", "reasoning",
            "cache_read", "cache_write", "total_tokens", "cost", "cost_kind", "ref",
        ]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)
    print(f"  Exported {len(records):,} events to {path}")
    return 0
