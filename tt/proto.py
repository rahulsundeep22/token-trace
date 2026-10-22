"""Minimal protobuf wire-format reader used by the Antigravity adapter.

No schema files are published for Antigravity's conversation databases, so we
decode the handful of fields we need directly from the wire format. This is the
same approach used by ccusage (rust/adapters/antigravity) and openusage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    number: int
    wire: int
    value: int | bytes

    @property
    def is_bytes(self) -> bool:
        return self.wire == 2

    @property
    def is_varint(self) -> bool:
        return self.wire == 0


def read_varint(buf: bytes, offset: int = 0) -> tuple[int | None, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(buf):
            return None, offset
        byte = buf[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
    return None, offset


def parse_fields(buf: bytes) -> list[Field]:
    fields: list[Field] = []
    offset = 0
    while offset < len(buf):
        tag, offset = read_varint(buf, offset)
        if tag is None or tag == 0:
            break
        number, wire = tag >> 3, tag & 7
        if number == 0:
            break
        if wire == 0:
            value, offset = read_varint(buf, offset)
            if value is None:
                break
            fields.append(Field(number, wire, value))
        elif wire == 2:
            length, offset = read_varint(buf, offset)
            if length is None or offset + length > len(buf):
                break
            fields.append(Field(number, wire, buf[offset : offset + length]))
            offset += length
        elif wire == 1:
            offset += 8
        elif wire == 5:
            offset += 4
        else:
            break
    return fields


def get_bytes(fields: list[Field], number: int) -> bytes | None:
    for field in reversed(fields):
        if field.number == number and field.is_bytes:
            return field.value  # type: ignore[return-value]
    return None


def get_all_bytes(fields: list[Field], number: int) -> list[bytes]:
    return [
        field.value  # type: ignore[misc]
        for field in fields
        if field.number == number and field.is_bytes
    ]


def get_varint(fields: list[Field], number: int) -> int | None:
    for field in reversed(fields):
        if field.number == number and field.is_varint:
            return field.value  # type: ignore[return-value]
    return None


def get_text(fields: list[Field], number: int) -> str | None:
    raw = get_bytes(fields, number)
    if not raw:
        return None
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    return text or None


def string_candidates(buf: bytes, *, min_length: int = 12, depth: int = 0) -> list[str]:
    """Recursively pull printable strings out of a protobuf blob.

    Used only for human-readable session titles; never for token accounting.
    """
    if depth > 8:
        return []
    out: list[str] = []
    for field in parse_fields(buf):
        if not field.is_bytes:
            continue
        chunk = field.value  # type: ignore[assignment]
        try:
            text = chunk.decode("utf-8")
            if len(text) >= min_length and " " in text:
                out.append(text)
        except UnicodeDecodeError:
            pass
        out.extend(string_candidates(chunk, min_length=min_length, depth=depth + 1))
    return out


def timestamp_ms(blob: bytes | None) -> int | None:
    """Decode google.protobuf.Timestamp (field 1 seconds, field 2 nanos)."""
    if not blob:
        return None
    fields = parse_fields(blob)
    seconds = get_varint(fields, 1)
    if not seconds:
        return None
    nanos = get_varint(fields, 2) or 0
    return int(seconds) * 1000 + min(int(nanos), 999_999_999) // 1_000_000
