"""Übersetzungen für den WDA Konfigurator (gettext-Prinzip).

Im Code stehen die englischen Texte, verpackt in T("…"). Jede Sprache ist eine Datei
locales/<code>.json mit {"English text": "Übersetzung"}. Fehlt ein Eintrag, wird Englisch
angezeigt. Regionale Varianten (z. B. es-419) dürfen unvollständig sein und verweisen per
"_fallback" auf die Hauptdatei (z. B. es-ES).

Angeboten werden genau die Sprachen, die auch der Wireless Display Adapter kennt.
"""
import json
import os
import sys
from pathlib import Path

# Code → Name in der eigenen Sprache (Reihenfolge = Anzeige im Auswahlfeld)
LANGUAGES = {
    "en-US": "English",
    "da-DK": "Dansk",
    "de-DE": "Deutsch",
    "es-ES": "Español (España)",
    "es-419": "Español (Latinoamérica)",
    "fi-FI": "Suomi",
    "fr-FR": "Français (France)",
    "fr-CA": "Français (Canada)",
    "it-IT": "Italiano",
    "ja-JP": "日本語",
    "ko-KR": "한국어",
    "nb-NO": "Norsk bokmål",
    "nl-NL": "Nederlands",
    "pt-BR": "Português (Brasil)",
    "pt-PT": "Português (Portugal)",
    "ru-RU": "Русский",
    "sv-SE": "Svenska",
    "th-TH": "ไทย",
    "zh-CN": "中文(简体)",
    "zh-TW": "中文(繁體)",
}
DEFAULT = "en-US"

_table = {}
_current = DEFAULT


def _locale_dir():
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "locales"


def _read(code):
    p = _locale_dir() / f"{code}.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    fallback = data.pop("_fallback", None)
    merged = _read(fallback) if fallback else {}
    merged.update(data)
    return merged


def set_language(code):
    """Sprache umschalten (unbekannte Codes → Englisch)."""
    global _table, _current
    _current = code if code in LANGUAGES else DEFAULT
    _table = {} if _current == DEFAULT else _read(_current)
    return _current


def current():
    return _current


def T(text):
    """Übersetzung des englischen Textes in die aktuelle Sprache (sonst der Text selbst)."""
    return _table.get(text) or text


# --- gespeicherte Einstellung (%APPDATA%\WDA-Konfigurator\settings.json) -------------
def _settings_file():
    return Path(os.environ.get("APPDATA", Path.home())) / "WDA-Konfigurator" / "settings.json"


def load_saved_language():
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8")).get("language", DEFAULT)
    except (OSError, ValueError):
        return DEFAULT


def save_language(code):
    f = _settings_file()
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        data = {}
    data["language"] = code
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass
