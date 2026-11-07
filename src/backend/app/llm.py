"""Обёртка над LLM: Anthropic API или mock (для запуска без ключа и для тестов)."""
import json
import logging
import re

from . import prompts
from .questions import NAME_KEYS, TAG_KEYS

log = logging.getLogger(__name__)


def _json_from_text(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    for opener, closer in (("[", "]"), ("{", "}")):
        s, e = text.find(opener), text.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    return None


class AnthropicLLM:
    def __init__(self, cfg):
        import anthropic  # ленивый импорт
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self.model = cfg.anthropic_model

    def _call(self, system, user, max_tokens=800):
        resp = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    def listener_reply(self, settings, question_text, transcript):
        user = (f"The question that was asked: {question_text or '(free storytelling)'}\n\n"
                f"What the person said:\n{transcript}\n\nYour short reply:")
        return self._call(prompts.listener_system(settings), user, 200)

    def extract_facts(self, transcript, keys, module_titles=None):
        user = (f"Transcript:\n{transcript}\n\nAllowed keys: {sorted(keys)}.\n"
                "Return JSON: {\"tags\": {key: true|false}, \"names\": {\"partner_name\": str, \"birth_year\": int, \"birth_place\": str}, "
                "\"avoid_modules\": [module ids the person asks NOT to talk about]}. Omit anything not clearly stated."
                + (f"\nModule ids and titles: {json.dumps(module_titles, ensure_ascii=False)}" if module_titles else ""))
        data = _json_from_text(self._call(prompts.extract_system(), user, 400))
        return data if isinstance(data, dict) else {}

    def extract_events(self, transcript):
        data = _json_from_text(self._call(prompts.events_system(), f"Transcript:\n{transcript}", 1200))
        return data if isinstance(data, list) else []

    def write_chapter(self, settings, title, qa_pairs):
        body = "\n\n".join(f"[Question: {q}]\n{a}" for q, a in qa_pairs)
        return self._call(prompts.chapter_system(settings), f"Chapter theme: {title}\n\nTranscripts:\n{body}", 2500)

    def comic_scenes(self, chapter_text):
        data = _json_from_text(self._call(prompts.comic_system(), f"Chapter:\n{chapter_text}", 1200))
        return data if isinstance(data, list) else []

    def recap(self, settings, transcripts):
        return self._call(prompts.recap_system(settings), "Today's transcripts:\n" + "\n---\n".join(transcripts), 250)


class MockLLM:
    """Детерминированная заглушка: позволяет пройти весь поток без ключа. Не для продакшена."""
    REPLIES = ["Понимаю.", "Спасибо, что рассказываете.", "Это важно. Я слушаю.", "Как интересно."]
    KEYWORDS = {
        "children": ["дети", "детей", "сын", "дочь", "kinder", "sohn", "tochter"],
        "grandchildren": ["внук", "внучк", "enkel"],
        "siblings": ["брат", "сестр", "bruder", "schwester"],
        "partner_now": ["жена", "муж ", "мужем", "ehefrau", "ehemann"],
        "pets": ["собак", "кошк", "hund", "katze"],
        "career": ["работал", "работала", "arbeitete", "beruf"],
        "military": ["армия", "армии", "служил", "bundeswehr"],
        "moved": ["переех", "zog um", "umgezogen"],
        "emigrated": ["эмигр", "ausgewandert", "aussiedler"],
    }

    def __init__(self):
        self.n = 0

    def listener_reply(self, settings, question_text, transcript):
        self.n += 1
        return self.REPLIES[self.n % len(self.REPLIES)]

    def extract_facts(self, transcript, keys, module_titles=None):
        low = transcript.lower()
        tags = {k: True for k, words in self.KEYWORDS.items() if k in keys and any(w in low for w in words)}
        names = {}
        m = re.search(r"(19\d\d)", transcript)
        if m and "birth_year" in keys:
            names["birth_year"] = int(m.group(1))
        return {"tags": tags, "names": names}

    def extract_events(self, transcript):
        out = []
        for m in re.finditer(r"(?i)\bв (\d{4}) году ([^.!?\n]+)", transcript):
            out.append({"title": m.group(2).strip()[:60], "year": int(m.group(1)), "date_text": m.group(1),
                        "place": None, "people": [], "summary": m.group(0).strip()})
        return out

    def write_chapter(self, settings, title, qa_pairs):
        return "\n\n".join(a for _, a in qa_pairs)

    def comic_scenes(self, chapter_text):
        paras = [p for p in chapter_text.split("\n\n") if p.strip()][:4]
        return [{"title": f"Сцена {i + 1}", "visual": p[:120], "caption": p[:60]} for i, p in enumerate(paras)]

    def recap(self, settings, transcripts):
        return "Спасибо, что поделились сегодня. Я всё сохранил."


def make_llm(cfg):
    if cfg.llm_provider == "anthropic":
        return AnthropicLLM(cfg)
    return MockLLM()


def clean_extraction(result, allowed_keys, gate_open, sensitive_tags):
    """Фильтрует ответ модели: только разрешённые ключи, только булевы теги, чувствительные только при согласии."""
    tags, names = {}, {}
    for k, v in (result.get("tags") or {}).items():
        if k in allowed_keys and k in TAG_KEYS and isinstance(v, bool):
            if k in sensitive_tags and not gate_open:
                continue
            tags[k] = v
    for k, v in (result.get("names") or {}).items():
        if k in allowed_keys and k in NAME_KEYS and v not in (None, ""):
            names[k] = v
    avoid = result.get("avoid_modules") if "avoid_modules" in allowed_keys else None
    return tags, names, avoid if isinstance(avoid, list) else None
