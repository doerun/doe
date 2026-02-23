#!/usr/bin/env python3
"""Shared helpers for timestamped benchmark artifact paths."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


TIMESTAMP_RE = re.compile(r"(?:^|[._-])\d{8}T\d{6}Z(?:[._-]|$)")
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
FILE_SUFFIXES = {
    ".json",
    ".html",
    ".md",
    ".txt",
    ".ndjson",
    ".tsv",
    ".log",
    ".csv",
}


def utc_timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def resolve_timestamp(timestamp: str) -> str:
    candidate = timestamp.strip()
    if not candidate:
        return utc_timestamp_now()
    if re.fullmatch(r"\d{8}T\d{6}Z", candidate):
        return candidate
    raise ValueError(
        "invalid timestamp format: expected YYYYMMDDTHHMMSSZ "
        f"(received: {timestamp})"
    )


def is_timestamped_path(path: Path) -> bool:
    name = path.name
    return bool(TIMESTAMP_RE.search(name))


def with_timestamp(path: str | Path, timestamp: str, *, enabled: bool = True) -> Path:
    target = Path(path)
    if not enabled:
        return target
    if is_timestamped_path(target):
        return target
    if target.suffix.lower() in FILE_SUFFIXES:
        return target.with_name(f"{target.stem}.{timestamp}{target.suffix}")
    return target.with_name(f"{target.name}.{timestamp}")
