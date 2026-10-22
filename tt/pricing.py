"""Model naming, pricing and catalog helpers.

Prices are USD per one million tokens. They are API-equivalent list prices used
to estimate value when an app does not record a dollar cost itself (Antigravity
subscriptions, Claude Code, Codex). OpenCode records exact per-message cost and
that always wins.

Rates can be overridden in ~/.tokentrace/config.json under "pricing".
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

# Provider -> model -> {input, output, cache_read, cache_write, reasoning}
FALLBACK_PRICING: dict[str, dict[str, dict[str, float]]] = {
    "google": {
        "gemini-3.8-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
        "gemini-3.7-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
        "gemini-3.6-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
        "gemini-3.5-flash": {"input": 0.75, "output": 3.75, "cache_read": 0.075},
        "gemini-3-flash-preview": {"input": 0.5, "output": 3.0, "cache_read": 0.05},
        "gemini-3.1-pro": {"input": 2.0, "output": 12.0, "cache_read": 0.2},
        "gemini-3-pro": {"input": 2.0, "output": 12.0, "cache_read": 0.2},
        "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.5, "cache_read": 0.025},
        "gemini-2.5-pro": {"input": 1.25, "output": 10.0, "cache_read": 0.125},
        "gemini-2.5-flash": {"input": 0.3, "output": 2.5, "cache_read": 0.03},
        "gemini-2.5-flash-lite": {"input": 0.1, "output": 0.4, "cache_read": 0.01},
        "gemini-2.0-flash": {"input": 0.1, "output": 0.4, "cache_read": 0.025},
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0, "cache_read": 0.3125},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.3, "cache_read": 0.01875},
    },
    "anthropic": {
        "claude-opus-4-6": {"input": 5.0, "output": 25.0, "cache_read": 0.5},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
        "claude-4.5-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
        "claude-4.5-haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.1},
        "claude-4-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
        "claude-4-opus": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
        "claude-3-7-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
        "claude-3-5-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
        "claude-3-5-haiku": {"input": 0.8, "output": 4.0, "cache_read": 0.08},
    },
    "openai": {
        "gpt-5": {"input": 1.25, "output": 10.0, "cache_read": 0.125},
        "gpt-5-codex": {"input": 1.25, "output": 10.0, "cache_read": 0.125},
        "gpt-5-mini": {"input": 0.25, "output": 2.0, "cache_read": 0.025},
        "gpt-4.1": {"input": 2.0, "output": 8.0, "cache_read": 0.5},
        "gpt-4o": {"input": 2.5, "output": 10.0, "cache_read": 1.25},
        "gpt-oss-120b": {"input": 0.15, "output": 0.6, "cache_read": 0.015},
    },
    "deepseek": {
        "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "cache_read": 0.022, "reasoning": 1.98},
        "deepseek-v4.1-flash": {"input": 0.3, "output": 1.2, "cache_read": 0.006},
        "deepseek-v4-flash": {"input": 0.15, "output": 0.6, "cache_read": 0.003, "reasoning": 0.6},
        "deepseek-v4-flash-free": {"input": 0, "output": 0, "cache_read": 0},
        "deepseek-v4.1-flash-free": {"input": 0, "output": 0, "cache_read": 0},
    },
}

EFFORT_SUFFIXES = ("-high", "-medium", "-low", "-minimal", "-tiered", "-thinking", "-n")


def pretty_model(model: str | None) -> str:
    if not model:
        return "Unknown model"
    name = model.split("/")[-1]
    name = name.replace("_", "-")
    parts = []
    for piece in name.split("-"):
        if piece.lower() in {"gpt", "oss", "ai"}:
            parts.append(piece.upper())
        elif piece[:1].isdigit():
            parts.append(piece)
        else:
            parts.append(piece[:1].upper() + piece[1:])
    return " ".join(parts)


def model_variants(model: str) -> list[str]:
    """Candidate catalog keys for a raw model id, most specific first."""
    raw = (model or "").strip().lower()
    if not raw:
        return []
    raw = raw.split("/")[-1]
    candidates = [raw]
    for prefix in ("models/", "google/", "gemini/", "anthropic/", "openai/"):
        if raw.startswith(prefix):
            candidates.append(raw[len(prefix) :])
    if "-tiered" in raw:
        candidates.append(raw.replace("-tiered", ""))
    for suffix in EFFORT_SUFFIXES:
        if raw.endswith(suffix):
            candidates.append(raw[: -len(suffix)])
    if raw.endswith("-preview"):
        candidates.append(raw[: -len("-preview")])
    else:
        candidates.append(raw + "-preview")
    base = candidates[-1] if candidates else raw
    if base.startswith("gemini-pro-default") or base.startswith("gemini-3.1-pro"):
        candidates.append("gemini-3.1-pro")
    # Deduplicate while preserving order.
    seen: set[str] = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def load_local_catalog() -> dict[str, dict[str, dict]]:
    """Read the models.dev catalog OpenCode caches locally (no network)."""
    candidates = []
    env_dir = os.environ.get("OPENCODE_DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / "opencode.db")
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        candidates.append(Path(xdg) / "opencode" / "opencode.db")
    candidates.append(Path.home() / ".local" / "share" / "opencode" / "opencode.db")
    for path in candidates:
        if not path.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
            row = conn.execute("select value from kv where key='models-dev:catalog'").fetchone()
            conn.close()
            if not row:
                continue
            outer = json.loads(row[0])
            body = outer.get("body", "{}")
            catalog = json.loads(body) if isinstance(body, str) else body
            result: dict[str, dict[str, dict]] = {}
            for provider_id, provider in catalog.items():
                models = provider.get("models") or {}
                result[provider_id] = models
            if result:
                return result
        except Exception:
            continue
    return {}


class Pricing:
    def __init__(self, overrides: dict | None = None):
        self.catalog = load_local_catalog()
        self.overrides = overrides or {}

    def rates(self, model: str | None, provider: str) -> tuple[dict[str, float] | None, str | None]:
        if not model:
            return None, None
        # User overrides first: {"provider/model": {...}} or {"model": {...}}
        for key in (f"{provider}/{model}", model):
            if key in self.overrides:
                return self.overrides[key], "override"
        variants = model_variants(model)

        providers = [provider]
        if provider in {"opencode", "openrouter"}:
            providers = [provider, "google", "deepseek", "anthropic", "openai"]
        for prov in providers:
            models = self.catalog.get(prov, {})
            for variant in variants:
                entry = models.get(variant)
                if entry and entry.get("cost"):
                    return self._normalize_rates(entry["cost"]), "models.dev"
        for prov in providers:
            table = FALLBACK_PRICING.get(prov, {})
            for variant in variants:
                if variant in table:
                    return table[variant], "built-in"
        # Last resort: look across every provider for a matching model.
        for prov, models in self.catalog.items():
            for variant in variants:
                entry = models.get(variant)
                if entry and entry.get("cost"):
                    return self._normalize_rates(entry["cost"]), "models.dev"
        return None, None

    @staticmethod
    def _normalize_rates(cost: dict) -> dict[str, float]:
        rates = {
            "input": float(cost.get("input") or 0),
            "output": float(cost.get("output") or 0),
            "cache_read": float(cost.get("cache_read") or 0),
            "cache_write": float(cost.get("cache_write") or 0),
            "reasoning": float(cost.get("reasoning") or cost.get("output") or 0),
        }
        if not rates["cache_write"]:
            rates["cache_write"] = rates["input"] * 1.25
        return rates

    def estimate(
        self,
        model: str | None,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        cache_read: int,
        cache_write: int,
    ) -> tuple[float | None, str | None]:
        rates, source = self.rates(model, provider)
        if not rates:
            return None, None
        cost = (
            input_tokens * rates.get("input", 0)
            + output_tokens * rates.get("output", 0)
            + reasoning_tokens * rates.get("reasoning", rates.get("output", 0))
            + cache_read * rates.get("cache_read", 0)
            + cache_write * rates.get("cache_write", rates.get("input", 0) * 1.25)
        ) / 1_000_000
        return round(cost, 8), source
