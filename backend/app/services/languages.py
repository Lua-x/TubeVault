"""Human-readable names for subtitle language codes."""

from __future__ import annotations

_NAMES = {
    "ar": "Arabisch",
    "cs": "Tschechisch",
    "da": "Dänisch",
    "de": "Deutsch",
    "el": "Griechisch",
    "en": "Englisch",
    "es": "Spanisch",
    "fi": "Finnisch",
    "fr": "Französisch",
    "he": "Hebräisch",
    "hi": "Hindi",
    "hu": "Ungarisch",
    "id": "Indonesisch",
    "it": "Italienisch",
    "ja": "Japanisch",
    "ko": "Koreanisch",
    "nl": "Niederländisch",
    "no": "Norwegisch",
    "pl": "Polnisch",
    "pt": "Portugiesisch",
    "ro": "Rumänisch",
    "ru": "Russisch",
    "sv": "Schwedisch",
    "th": "Thailändisch",
    "tr": "Türkisch",
    "uk": "Ukrainisch",
    "vi": "Vietnamesisch",
    "zh": "Chinesisch",
}


def subtitle_label(lang: str, is_auto: bool) -> str:
    name = _NAMES.get(lang.split("-")[0].lower(), lang.upper())
    return f"{name} (automatisch)" if is_auto else name
