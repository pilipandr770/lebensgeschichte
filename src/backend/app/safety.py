"""Детектор кризисных фраз. Это страховочная сетка, а не диагностика: при срабатывании приложение
отвечает фиксированным спокойным текстом и не продолжает интервью. Список нужно расширять и тестировать."""
import re

_PATTERNS = [
    # русский
    r"не хочу жить", r"хочу умереть", r"покончить с собой", r"покончу с собой", r"убить себя",
    r"лучше бы я умер", r"лучше бы меня не было", r"не вижу смысла жить", r"наложить на себя руки",
    # немецкий
    r"nicht mehr leben", r"will sterben", r"umbringen", r"suizid", r"selbstmord", r"das leben nehmen",
    r"lieber tot", r"nicht mehr aufwachen",
    # английский
    r"kill myself", r"want to die", r"end my life", r"suicid",
]
_RE = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def detect_crisis(text: str) -> bool:
    return bool(text and _RE.search(text))
