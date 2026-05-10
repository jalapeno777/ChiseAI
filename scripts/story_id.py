#!/usr/bin/env python3
"""Shared story-id utilities for CI and PR automation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Bootstrap environment first (must be before any env access)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from config.bootstrap import bootstrap

bootstrap(load_env=True)

# Accepted canonical prefixes used across ChiseAI workflows.
_PREFIX_RE = r"(?:ST|CH|FT|REWARD|REPO|SAFETY|BRANCH|PAPER|RECON|PT|I|D)"
_STORY_ID_FULL_RE = re.compile(
    rf"^{_PREFIX_RE}(?:-[A-Z0-9]+)+$",
    re.IGNORECASE,
)
STORY_ID_RE = re.compile(rf"{_PREFIX_RE}-[A-Z0-9-]+", re.IGNORECASE)


def _trim_candidate(candidate: str) -> str:
    """Trim branch-tail slug segments after first non-digit segment post numeric core."""
    parts = [p for p in candidate.upper().split("-") if p]
    if len(parts) < 2:
        return candidate.upper()

    out = [parts[0]]
    digit_seen = False
    for seg in parts[1:]:
        has_digit = any(ch.isdigit() for ch in seg)
        if digit_seen and not has_digit:
            break
        out.append(seg)
        if has_digit:
            digit_seen = True
    return "-".join(out)


def is_valid_story_id_token(token: str) -> bool:
    """Return True when token matches full accepted story-id format with a digit."""
    normalized = token.strip().upper()
    if not _STORY_ID_FULL_RE.fullmatch(normalized):
        return False
    return any(ch.isdigit() for ch in normalized)


def extract_story_ids(text: str) -> list[str]:
    """Extract story-id-like tokens from free text."""
    out: list[str] = []
    seen: set[str] = set()
    for m in STORY_ID_RE.finditer((text or "").upper()):
        token = _trim_candidate(m.group(0))
        if is_valid_story_id_token(token) and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def contains_valid_story_id(text: str) -> bool:
    """Return True when text contains an accepted story id with at least one digit."""
    return any(any(ch.isdigit() for ch in token) for token in extract_story_ids(text))


def has_story_id_token(text: str, story_id: str) -> bool:
    """Return True when a specific story id token exists in text (case-insensitive)."""
    if not story_id.strip():
        return False
    token_re = re.compile(rf"\b{re.escape(story_id.strip())}\b", re.IGNORECASE)
    return bool(token_re.search(text or ""))


def normalize_story_id(story_id: str) -> str:
    """Trim and uppercase story id for deterministic title generation."""
    return story_id.strip().upper()


def ensure_story_id_prefix(story_id: str, title: str) -> str:
    """Prefix title with story id only when it is not already present as a token."""
    sid = normalize_story_id(story_id)
    base = (title or "").strip()
    if not base:
        return sid
    if has_story_id_token(base, sid):
        return base
    return f"{sid} {base}"
