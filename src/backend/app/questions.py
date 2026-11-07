"""Движок банка вопросов: безопасный парсер условий (без eval) и выбор следующего вопроса."""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

TAG_KEYS = {
    "partner_ever", "partner_now", "widowed", "divorced", "children", "grandchildren", "siblings",
    "mother_known", "father_known", "career", "self_employed", "homemaker", "retired", "military",
    "moved", "emigrated", "pets", "garden", "loss", "illness", "faith_ok", "hard_childhood",
}
NAME_KEYS = {"partner_name", "birth_year", "birth_place"}
# Ставятся только после согласия на чувствительный модуль (gate открыт).
SENSITIVE_TAGS = {"loss", "illness", "faith_ok", "hard_childhood"}
DEFAULT_TAGS = {"mother_known": True, "father_known": True}


# ---------- безопасный вычислитель условий ----------
class ExprError(ValueError):
    pass


_TOKEN = re.compile(r"\s*(\|\||&&|==|!=|!|\(|\)|'[^']*'|\"[^\"]*\"|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?)")


def _tokenize(s):
    s, pos, out = s.strip(), 0, []
    while pos < len(s):
        m = _TOKEN.match(s, pos)
        if not m:
            raise ExprError(f"Недопустимый символ в условии: {s[pos:pos + 12]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


def _truthy(v):
    if v is None or v == "unknown":
        return False
    return bool(v)


def _norm_eq(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b and type(a) == type(b)
    return str(a) == str(b)


class _Parser:
    def __init__(self, tokens, ctx):
        self.t, self.i, self.ctx = tokens, 0, ctx

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        tok = self.peek()
        if tok is None:
            raise ExprError("Неожиданный конец условия")
        self.i += 1
        return tok

    def parse(self):
        v = self.or_()
        if self.peek() is not None:
            raise ExprError(f"Лишний токен: {self.peek()!r}")
        return _truthy(v)

    def or_(self):
        left = self.and_()
        while self.peek() == "||":
            self.take()
            right = self.and_()
            left = _truthy(left) or _truthy(right)
        return left

    def and_(self):
        left = self.not_()
        while self.peek() == "&&":
            self.take()
            right = self.not_()
            left = _truthy(left) and _truthy(right)
        return left

    def not_(self):
        if self.peek() == "!":
            self.take()
            return not _truthy(self.not_())
        return self.cmp_()

    def cmp_(self):
        left = self.atom()
        p = self.peek()
        if p in ("==", "!="):
            self.take()
            right = self.rhs()
            eq = _norm_eq(left, right)
            return eq if p == "==" else not eq
        if p == "in":
            self.take()
            right = self.atom()
            return isinstance(right, (list, tuple, set, str)) and left in right
        return left

    def rhs(self):
        tok = self.peek()
        if tok and re.match(r"[A-Za-z_]", tok) and tok not in ("true", "false", "in"):
            self.take()
            return tok  # голый идентификатор справа от ==/!= это строковый литерал
        return self.atom()

    def atom(self):
        tok = self.take()
        if tok == "(":
            v = self.or_()
            if self.take() != ")":
                raise ExprError("Ожидалась )")
            return v
        if tok[0] in "'\"":
            return tok[1:-1]
        if re.match(r"-?\d", tok):
            return float(tok) if "." in tok else int(tok)
        if tok == "true":
            return True
        if tok == "false":
            return False
        if tok == "unknown":
            if self.take() != "(":
                raise ExprError("Ожидалась ( после unknown")
            name = self.take()
            if self.take() != ")":
                raise ExprError("Ожидалась )")
            v = self.ctx.get(name)
            return v is None or v == "unknown"
        if re.match(r"[A-Za-z_]", tok):
            return self.ctx.get(tok)
        raise ExprError(f"Неожиданный токен {tok!r}")


def evaluate(expr, ctx):
    if expr is None or str(expr).strip() == "":
        return True
    return _Parser(_tokenize(str(expr)), ctx).parse()


# ---------- контекст ----------
def build_ctx(profile):
    ctx = dict(DEFAULT_TAGS)
    ctx.update(profile.get("tags", {}))
    ctx.update(profile.get("settings", {}))
    # производные теги
    if any(ctx.get(k) is True for k in ("partner_now", "widowed", "divorced")) and ctx.get("partner_ever") is None:
        ctx["partner_ever"] = True
    by = ctx.get("birth_year")
    try:
        by = int(by)
    except (TypeError, ValueError):
        by = None
    if by and ctx.get("war_childhood") is None:
        ctx["war_childhood"] = 1925 <= by <= 1950
    return ctx


_PARTNER_FALLBACKS = [("с {partner}", "с вашим партнёром"), ("в {partner}", "в вашем партнёре"),
                      ("о {partner}", "о вашем партнёре")]


def fill_text(text, ctx):
    name = ctx.get("partner_name")
    if "{partner}" in text:
        if name:
            text = text.replace("{partner}", str(name))
        else:
            for old, new in _PARTNER_FALLBACKS:
                text = text.replace(old, new)
            text = text.replace("{partner}", "ваш партнёр")
    return text


# ---------- банк ----------
class QuestionBank:
    def __init__(self, data):
        self.meta = data.get("meta", {})
        self.modules = sorted(data["modules"], key=lambda m: m["order"])
        self.questions = data["questions"]
        self.by_id = {q["id"]: q for q in self.questions}
        self.mod_by_id = {m["id"]: m for m in self.modules}
        self.followups = data.get("followups", [])
        self.after_heavy = data.get("after_heavy", [])
        self.bright_ids = ["c10", "f1", "j1"]

    @classmethod
    def from_file(cls, path=None):
        path = Path(path) if path else DATA_DIR / "questions.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def validate(self):
        errors, seen = [], set()
        for q in self.questions:
            if q["id"] in seen:
                errors.append(f"Дубликат id: {q['id']}")
            seen.add(q["id"])
            if q.get("m") not in self.mod_by_id:
                errors.append(f"{q['id']}: неизвестный модуль {q.get('m')}")
            if q.get("p") not in (1, 2):
                errors.append(f"{q['id']}: поле p должно быть 1 или 2")
            for key in ("extract",):
                for k in q.get(key, []):
                    if k not in TAG_KEYS | NAME_KEYS | {"avoid_modules"}:
                        errors.append(f"{q['id']}: неизвестный тег в extract: {k}")
            try:
                evaluate(q.get("if"), {})
            except ExprError as e:
                errors.append(f"{q['id']}: ошибка в условии {q.get('if')!r}: {e}")
        for m in self.modules:
            try:
                evaluate(m.get("if"), {})
            except ExprError as e:
                errors.append(f"модуль {m['id']}: ошибка в условии: {e}")
        return errors

    # --- выбор следующего ---
    def _public(self, q, ctx):
        m = self.mod_by_id[q["m"]]
        return {"id": q["id"], "module": q["m"], "module_title": m["title"], "p": q["p"],
                "text": fill_text(q["q"], ctx), "sensitive": bool(q.get("sensitive"))}

    def _eligible(self, q, ctx, asked):
        return q["id"] not in asked and evaluate(q.get("if"), ctx)

    def _module_active(self, m, ctx, state, settings):
        if m["id"] in set(settings.get("avoid_modules", []) or []):
            return False
        if not evaluate(m.get("if"), ctx):
            return False
        return state["gates"].get(m["id"]) != "closed"

    def _remaining(self, m, ctx, asked, max_p):
        qs = [q for q in self.questions if q["m"] == m["id"] and q["p"] <= max_p and self._eligible(q, ctx, asked)]
        qs.sort(key=lambda q: q["p"])  # p1 раньше p2, порядок файла сохраняется (стабильная сортировка)
        return qs

    def next(self, ctx, state, settings):
        asked = state.get("asked", {})
        minutes = settings.get("session_minutes")
        try:
            minutes = int(minutes) if minutes is not None else 20
        except (TypeError, ValueError):
            minutes = 20
        max_p = 1 if 0 < minutes <= 10 else 2
        order_mode = settings.get("order_mode", "chronological")
        heavy_delay = (settings.get("role") == "listener" or settings.get("sad_response") == "change_topic") \
            and state.get("sessions_done", 0) < 3

        def wrap(q):
            out = {"type": "question", "question": self._public(q, ctx)}
            if state.get("last_sensitive") and self.after_heavy:
                out["bridge"] = self.after_heavy[state.get("bridge_idx", 0) % len(self.after_heavy)]
            return out

        # 1) знакомство всегда первым
        intro = self.mod_by_id.get("intro")
        if intro:
            rem = self._remaining(intro, ctx, asked, 2)
            if rem:
                return wrap(rem[0])

        # 2) «сначала самое яркое»
        if order_mode == "brightest_first":
            for qid in self.bright_ids:
                q = self.by_id.get(qid)
                if q and self._eligible(q, ctx, asked) and self._module_active(self.mod_by_id[q["m"]], ctx, state, settings):
                    return wrap(q)

        # 3) выбор темы пользователем
        if order_mode in ("by_theme", "free"):
            cur = state.get("current_module")
            if cur and cur in self.mod_by_id:
                m = self.mod_by_id[cur]
                if self._module_active(m, ctx, state, settings):
                    rem = self._remaining(m, ctx, asked, max_p)
                    if rem:
                        return wrap(rem[0])
            options = []
            for m in self.modules:
                if m["id"] == "intro" or not self._module_active(m, ctx, state, settings):
                    continue
                if self._remaining(m, ctx, asked, max_p):
                    options.append({"id": m["id"], "title": m["title"], "gated": bool(m.get("gate"))})
            if not options:
                return {"type": "done"}
            return {"type": "choose_module", "modules": options}

        # 4) хронология
        for m in self.modules:
            if m["id"] == "intro" or not self._module_active(m, ctx, state, settings):
                continue
            rem = self._remaining(m, ctx, asked, max_p)
            if not rem:
                continue
            if m.get("gate"):
                if heavy_delay:
                    continue
                if state["gates"].get(m["id"]) != "open":
                    return {"type": "gate", "module": {"id": m["id"], "title": m["title"]}, "text": m.get("gate_text", "")}
            return wrap(rem[0])
        return {"type": "done"}


def record_answer(state, qid, status="answered", sensitive=False):
    state["asked"][qid] = status
    if status == "answered":
        state["consecutive_skips"] = 0
        was = state.get("last_sensitive")
        state["last_sensitive"] = bool(sensitive)
        if was:
            state["bridge_idx"] = state.get("bridge_idx", 0) + 1
    else:
        state["consecutive_skips"] = state.get("consecutive_skips", 0) + 1
    return state
