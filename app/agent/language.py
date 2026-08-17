"""Automatic language detection for caller utterances.

Deliberately avoids calling the LLM for this (would add cost/latency to
every turn). Detection order: Unicode script (splits {hi, mr} / ta / kn /
Latin instantly and deterministically) -> Devanagari marker words to break
the Hindi/Marathi tie -> explicit language-name mentions (e.g. a one-word
"English" reply must override an established language, so length alone
never gates detection) -> romanized-Hindi keywords -> `langdetect` for
everything else, falling back to the previous turn's language only for
pure filler replies ("ok", "yeah") or outright detection failure.

Won't perfectly classify heavily code-mixed sentences -- see README
"Limitations".
"""

from __future__ import annotations

import re
import string
from typing import Optional

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "mr": "Marathi",
    "ta": "Tamil",
    "kn": "Kannada",
}

DEFAULT_LANGUAGE = "en"

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_TAMIL_RE = re.compile(r"[஀-௿]")
_KANNADA_RE = re.compile(r"[ಀ-೿]")

_HINDI_MARKERS = {
    "है", "हूं", "हूँ", "हैं", "क्या", "चाहिए", "मुझे", "आपका", "कैसे",
    "मेरा", "मेरी", "हमें", "नहीं", "और", "के", "लिए", "का", "की",
}
_MARATHI_MARKERS = {
    "आहे", "आहात", "आहेत", "काय", "पाहिजे", "मला", "तुमचं", "कसं",
    "कशी", "माझं", "माझी", "नाही", "आणि", "साठी", "चा", "ची",
}

_ROMAN_HINDI_MARKERS = {
    "hai", "hain", "chahiye", "mujhe", "kaise", "kitna", "kitni", "paisa",
    "rupaye", "parivar", "namaste", "dhanyavad", "aap", "aapka", "mera",
    "meri", "humein", "nahi", "haan", "acha", "theek", "bhai", "ke", "liye",
    "ka", "ki", "ko", "se", "kya",
}

_LANGUAGE_NAME_HINTS: dict[str, set[str]] = {
    "en": {"english", "eng"},
    "hi": {"hindi"},
    "mr": {"marathi"},
    "ta": {"tamil"},
    "kn": {"kannada"},
}

_FILLER_WORDS = {"ok", "okay", "yes", "yeah", "yep", "hmm", "hm", "no"}

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _script_of(text: str) -> Optional[str]:
    """Return the dominant Indic script in `text`, or None for Latin/mixed."""

    if _DEVANAGARI_RE.search(text):
        return "devanagari"
    if _TAMIL_RE.search(text):
        return "tamil"
    if _KANNADA_RE.search(text):
        return "kannada"
    return None


def _classify_devanagari(text: str) -> str:
    """Disambiguate Hindi vs Marathi within Devanagari-script text."""

    words = text.split()
    hindi_hits = sum(1 for w in words if w.strip(string.punctuation) in _HINDI_MARKERS)
    marathi_hits = sum(1 for w in words if w.strip(string.punctuation) in _MARATHI_MARKERS)
    if marathi_hits > hindi_hits:
        return "mr"
    return "hi"


def _looks_like_romanized_hindi(text: str) -> bool:
    words = [w.lower().translate(_PUNCT_TABLE) for w in text.split()]
    words = [w for w in words if w]
    if not words:
        return False
    hits = sum(1 for w in words if w in _ROMAN_HINDI_MARKERS)
    return hits >= 1 and (hits / len(words)) >= 0.15


def _langdetect_guess(text: str) -> Optional[str]:
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0  # deterministic results across calls
        return detect(text)
    except Exception:
        return None


def detect_language(text: str, previous_language: Optional[str] = None) -> str:
    """Detect the ISO 639-1 code of `text` from the set of supported languages."""

    text = (text or "").strip()
    if not text:
        return previous_language if previous_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    script = _script_of(text)
    if script == "devanagari":
        return _classify_devanagari(text)
    if script == "tamil":
        return "ta"
    if script == "kannada":
        return "kn"

    words = [w.lower().translate(_PUNCT_TABLE) for w in text.split()]
    words = [w for w in words if w]
    if not words:
        return previous_language if previous_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    for lang, hints in _LANGUAGE_NAME_HINTS.items():
        if any(w in hints for w in words):
            return lang

    if _looks_like_romanized_hindi(text):
        return "hi"

    if previous_language in SUPPORTED_LANGUAGES and all(w in _FILLER_WORDS for w in words):
        return previous_language

    guess = _langdetect_guess(text)
    if guess in SUPPORTED_LANGUAGES:
        return guess

    if previous_language in SUPPORTED_LANGUAGES:
        return previous_language

    return DEFAULT_LANGUAGE


class LanguageTracker:
    """Small stateful helper used by the voice agent to track language per session."""

    def __init__(self, initial_language: str = DEFAULT_LANGUAGE) -> None:
        self.current_language = initial_language
        self.detected_languages: set[str] = {initial_language}

    def update(self, text: str) -> str:
        """Detect the language of `text`, update tracked state, and return it."""

        detected = detect_language(text, previous_language=self.current_language)
        self.current_language = detected
        self.detected_languages.add(detected)
        return detected
