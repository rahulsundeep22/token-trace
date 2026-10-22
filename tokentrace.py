#!/usr/bin/env python3
"""TokenTrace command line entry point."""

from __future__ import annotations

import argparse
import sys

from tt.config import load_config, save_config
from tt.report import cmd_doctor, cmd_export, cmd_report, cmd_scan, print_scan_report
from tt.scan import scan_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tokentrace",
        description="Track AI token usage across OpenCode, Antigravity, Claude Code, Codex and Gemini CLI.",
    )
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="scan every supported app and update the local database")
    scan.set_defaults(func=lambda args: cmd_scan(load_config()))

    serve = sub.add_parser("serve", help="start the local dashboard")
    serve.add_argument("--port", type=int, default=8787, help="preferred port (default 8787)")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default loopback)")
    serve.add_argument("--no-open", action="store_true", help="do not open a browser")
    serve.add_argument("--no-scan", action="store_true", help="skip the scan on startup")
    serve.add_argument("--interval", type=int, default=None, help="background rescan interval in seconds")
    serve.add_argument("--verbose", action="store_true", help="log HTTP requests")

    report = sub.add_parser("report", help="print a terminal usage report")
    report.add_argument("--days", type=int, default=30, help="number of days (0 = all time)")

    sub.add_parser("doctor", help="show detected apps, paths and database status")

    export = sub.add_parser("export", help="export raw usage events")
    export.add_argument("--days", type=int, default=30, help="number of days (0 = all time)")
    export.add_argument("--out", default="tokentrace-export.csv", help="output file")
    export.add_argument("--format", choices=["csv", "json"], default="csv")

    sub.add_parser("init", help="create the config file and run a first scan")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()

    if args.command in (None, "serve"):
        from tt.server import serve

        interval = args.interval if getattr(args, "interval", None) is not None else int(config.get("scan_interval_seconds") or 120)
        if not getattr(args, "no_scan", False):
            print("  Scanning local AI apps...")
            try:
                report = scan_all(config)
                print_scan_report(report)
            except Exception as exc:
                print(f"  Initial scan failed: {exc}")
        serve(
            config,
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8787),
            open_browser=not getattr(args, "no_open", False),
            scan_interval=interval,
            verbose=getattr(args, "verbose", False),
        )
        return 0

    if args.command == "init":
        save_config(config)
        print(f"  Config written to {config}")
        return cmd_scan(config)

    if args.command == "scan":
        return args.func(args)
    if args.command == "report":
        return cmd_report(config, args.days)
    if args.command == "doctor":
        return cmd_doctor(config)
    if args.command == "export":
        return cmd_export(config, args.days, args.out, args.format)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
