"""Minimal translation support (gettext-like, no build step, standard library only).

Source strings in the code are English. ``tr("Save")`` returns the translation from
``ksnapmark/translations/<lang>.py`` (a dict named ``CATALOG``) or the English text itself.

The language is chosen once at start-up:
1. environment variable ``KSNAPMARK_LANG`` (``en`` / ``de``), or ``language`` in config.toml
   (``auto`` = follow the system),
2. the system language (``LANGUAGE``, ``LC_ALL``, ``LC_MESSAGES``, ``LANG``),
3. English.
"""

from __future__ import annotations

import importlib
import os
import tomllib
from pathlib import Path

SUPPORTED = {"en": "English", "de": "Deutsch"}

CATALOG: dict[str, str] = {}
LANG = "en"


def configured_language() -> str:
    """Value of the ``language`` setting: ``auto`` or a supported code."""
    forced = os.environ.get("KSNAPMARK_LANG", "").strip().lower()
    if forced:
        return forced
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    try:
        with open(Path(base) / "ksnapmark" / "config.toml", "rb") as f:
            return str(tomllib.load(f).get("language", "auto")).strip().lower()
    except (OSError, ValueError):
        return "auto"


def system_language() -> str:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for value in os.environ.get(var, "").split(":"):
            code = value.split(".")[0].split("@")[0].split("_")[0].strip().lower()
            if code in ("", "c", "posix"):
                continue
            if code in SUPPORTED:
                return code
    return "en"


def detect() -> str:
    wanted = configured_language()
    return wanted if wanted in SUPPORTED else system_language()


def set_language(lang: str) -> str:
    """Activate a language (falls back to English) and return the active code."""
    global LANG, CATALOG
    lang = lang if lang in SUPPORTED else "en"
    CATALOG = {}
    if lang != "en":
        try:
            CATALOG = importlib.import_module(f"{__package__}.translations.{lang}").CATALOG
        except ImportError:
            lang = "en"
    LANG = lang
    return lang


def tr(text: str) -> str:
    return CATALOG.get(text, text)


set_language(detect())
