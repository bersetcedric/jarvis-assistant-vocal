"""Langues proposees pour la narration et les sous-titres.

La liste sert de suggestion : toute autre langue peut etre saisie librement.
Le code ISO n'est transmis a la voix que si le modele vocal le reconnait.
"""

from __future__ import annotations

import re

LANGUES = {
    "Français": "fr", "English": "en", "Español": "es", "Português": "pt", "Deutsch": "de",
    "Italiano": "it", "Nederlands": "nl", "العربية": "ar", "中文": "zh", "日本語": "ja", "한국어": "ko",
    "हिन्दी": "hi", "বাংলা": "bn", "اردو": "ur", "فارسی": "fa", "Türkçe": "tr", "Русский": "ru",
    "Українська": "uk", "Polski": "pl", "Čeština": "cs", "Slovenčina": "sk", "Magyar": "hu",
    "Română": "ro", "Български": "bg", "Ελληνικά": "el", "Svenska": "sv", "Norsk": "no", "Dansk": "da",
    "Suomi": "fi", "Hrvatski": "hr", "Srpski": "sr", "Slovenščina": "sl", "Lietuvių": "lt",
    "Latviešu": "lv", "Eesti": "et", "עברית": "he", "ไทย": "th", "Tiếng Việt": "vi",
    "Bahasa Indonesia": "id", "Bahasa Melayu": "ms", "Filipino": "fil", "தமிழ்": "ta", "తెలుగు": "te",
    "मराठी": "mr", "ગુજરાતી": "gu", "ਪੰਜਾਬੀ": "pa", "ಕನ್ನಡ": "kn", "മലയാളം": "ml", "नेपाली": "ne",
    "සිංහල": "si", "ខ្មែរ": "km", "မြန်မာ": "my", "Kiswahili": "sw", "አማርኛ": "am", "Hausa": "ha",
    "Yorùbá": "yo", "isiZulu": "zu", "Afrikaans": "af", "Català": "ca", "Euskara": "eu", "Galego": "gl",
    "Gaeilge": "ga", "Cymraeg": "cy", "Íslenska": "is", "Shqip": "sq", "Македонски": "mk",
    "Հայերեն": "hy", "ქართული": "ka", "Azərbaycanca": "az", "Қазақша": "kk", "Oʻzbekcha": "uz",
    "Монгол": "mn", "Kreyòl ayisyen": "ht", "Malagasy": "mg", "Wolof": "wo", "Lingála": "ln",
    "Esperanto": "eo", "Latina": "la",
}
# Codes acceptes par le modele vocal ElevenLabs « flash v2.5 ».
CODES_VOIX = {"en", "ja", "zh", "de", "hi", "fr", "ko", "pt", "it", "es", "id", "nl", "tr", "fil", "pl",
              "sv", "bg", "ro", "ar", "cs", "el", "fi", "hr", "ms", "sk", "da", "ta", "uk", "ru", "hu",
              "no", "vi"}
_PAR_NOM = {nom.casefold(): nom for nom in LANGUES}


def normaliser(langue: str) -> str:
    """Nettoie la langue saisie ; vide ou illisible -> Français."""
    langue = re.sub(r"[^\w\s'’()-]", "", " ".join(str(langue or "").split()))[:40].strip()
    return _PAR_NOM.get(langue.casefold(), langue) or "Français"


def code_voix(langue: str) -> str | None:
    code = LANGUES.get(langue)
    return code if code in CODES_VOIX else None
