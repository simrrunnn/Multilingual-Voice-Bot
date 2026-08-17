"""Tests for the offline language-detection heuristic (app.agent.language).

See app/agent/language.py for the documented three-stage approach
(Unicode script detection -> Devanagari marker words -> langdetect for
Latin-script text) that these tests exercise.
"""

from __future__ import annotations

from app.agent.language import LanguageTracker, detect_language


def test_detects_plain_english():
    assert detect_language("Hi, I would like health insurance for my family please") == "en"


def test_detects_hindi_devanagari():
    text = "मुझे अपने परिवार के लिए हेल्थ इंश्योरेंस चाहिए"
    assert detect_language(text) == "hi"


def test_detects_marathi_devanagari():
    text = "मला माझ्या कुटुंबासाठी हेल्थ इन्शुरन्स पाहिजे आहे"
    assert detect_language(text) == "mr"


def test_detects_tamil_script():
    text = "எனக்கு எனது குடும்பத்திற்கு ஆரோக்கிய காப்பீடு வேண்டும்"
    assert detect_language(text) == "ta"


def test_detects_kannada_script():
    text = "ನನಗೆ ನನ್ನ ಕುಟುಂಬಕ್ಕೆ ಆರೋಗ್ಯ ವಿಮೆ ಬೇಕು"
    assert detect_language(text) == "kn"


def test_detects_romanized_hindi_from_keywords():
    assert detect_language("mujhe insurance chahiye mere parivar ke liye") == "hi"


def test_short_ambiguous_utterance_sticks_to_previous_language():
    assert detect_language("haan", previous_language="hi") == "hi"
    assert detect_language("ok", previous_language="en") == "en"


def test_naming_the_language_overrides_previous_language_even_when_short():
    # Regression test: a caller who switches back to a language they used
    # earlier must be detected even in a one- or two-word reply -- language
    # detection must never just stick to whatever was active before.
    assert detect_language("english", previous_language="hi") == "en"
    assert detect_language("English please", previous_language="hi") == "en"
    assert detect_language("hindi", previous_language="en") == "hi"
    assert detect_language("switch to marathi", previous_language="en") == "mr"


def test_short_non_filler_phrase_still_gets_real_detection():
    # Not a filler word and not a language name, but still short -- must not
    # be blindly stuck to the previous language.
    assert detect_language("thank you", previous_language="hi") == "en"


def test_empty_text_falls_back_to_previous_language_or_default():
    assert detect_language("", previous_language="ta") == "ta"
    assert detect_language("   ") == "en"


def test_language_switch_mid_conversation():
    # Caller starts in Hindi, then switches to English mid-call.
    hindi_turn = detect_language("मुझे अपने परिवार के लिए हेल्थ इंश्योरेंस चाहिए")
    english_turn = detect_language("My budget is twenty thousand rupees per year", previous_language=hindi_turn)
    assert hindi_turn == "hi"
    assert english_turn == "en"


def test_language_tracker_updates_and_accumulates_detected_languages():
    tracker = LanguageTracker(initial_language="en")
    tracker.update("मुझे अपने परिवार के लिए हेल्थ इंश्योरेंस चाहिए")
    assert tracker.current_language == "hi"
    tracker.update("My budget is twenty thousand")
    assert tracker.current_language == "en"
    assert tracker.detected_languages == {"en", "hi"}


def test_detect_language_only_returns_supported_codes():
    samples = [
        "Hello there, how are you?",
        "मुझे मदद चाहिए",
        "मला मदत हवी आहे",
        "எனக்கு உதவி தேவை",
        "ನನಗೆ ಸಹಾಯ ಬೇಕು",
    ]
    for text in samples:
        assert detect_language(text) in {"en", "hi", "mr", "ta", "kn"}
