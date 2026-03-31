"""Localized state-message helpers for Atrea aMotion."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LANGUAGE = "en"
_TRANSLATIONS_DIR = Path(__file__).parent / "translations"
_SECTION = "state_messages"


def language_candidates(language: str | None) -> list[str]:
    """Return translation candidates ordered by preference."""
    candidates: list[str] = []
    if isinstance(language, str) and language.strip():
        normalized = language.strip().replace("_", "-").lower()
        candidates.append(normalized)
        base = normalized.split("-", 1)[0]
        if base not in candidates:
            candidates.append(base)
    if DEFAULT_LANGUAGE not in candidates:
        candidates.append(DEFAULT_LANGUAGE)
    return candidates


@lru_cache(maxsize=None)
def load_state_messages(language: str) -> dict[str, str]:
    """Load translated websocket state messages for a language."""
    path = _TRANSLATIONS_DIR / f"{language}.json"
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    section = payload.get(_SECTION, {})
    if not isinstance(section, dict):
        return {}

    return {
        str(key): str(value)
        for key, value in section.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def translate_state_message(language: str | None, code: str | None) -> str | None:
    """Return a localized message for a websocket state code."""
    if not code:
        return None

    for candidate in language_candidates(language):
        message = load_state_messages(candidate).get(code)
        if message:
            return message
    return None


def translation_key_for(code: str | None) -> str | None:
    """Build a translation key-like path for UI payloads."""
    if not code:
        return None
    return f"{_SECTION}.{code}"


def hass_language(hass: Any) -> str | None:
    """Read the active Home Assistant language if available."""
    config = getattr(hass, "config", None)
    language = getattr(config, "language", None)
    return language if isinstance(language, str) and language else None
