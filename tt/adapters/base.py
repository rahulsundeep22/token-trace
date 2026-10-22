"""Shared adapter types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Instance:
    source: str
    source_label: str
    surface: str
    account_key: str
    path: str
    detail: str = ""


@dataclass
class Event:
    source: str
    source_label: str
    surface: str
    account_key: str
    session_id: str
    native_id: str
    ts: int
    model: str | None = None
    model_label: str | None = None
    session_title: str | None = None
    project: str | None = None
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float | None = None
    cost_kind: str = "estimated"
    price_provider: str = ""
    ref: str = ""

    @property
    def tokens(self) -> int:
        return self.input + self.output + self.reasoning + self.cache_read + self.cache_write

    def has_tokens(self) -> bool:
        return self.tokens > 0


@dataclass
class ScanResult:
    events: list[Event] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    instances: int = 0
    sessions: int = 0


def basename(path: str | None) -> str | None:
    if not path:
        return None
    cleaned = path.replace("\\", "/").rstrip("/")
    if not cleaned:
        return None
    return cleaned.split("/")[-1] or None
