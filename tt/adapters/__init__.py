"""Adapter registry."""

from __future__ import annotations

from . import antigravity, claude_code, codex, gemini_cli, opencode

ADAPTERS = [
    opencode,
    antigravity,
    claude_code,
    codex,
    gemini_cli,
]

ADAPTER_MAP = {module.SOURCE: module for module in ADAPTERS}
