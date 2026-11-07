import unittest

from app.questions import ExprError, QuestionBank, build_ctx, evaluate, record_answer
from app.db import DEFAULT_STATE
import copy


def fresh_state():
    return copy.deepcopy(DEFAULT_STATE)


class ExprTests(unittest.TestCase):
    def test_basic(self):
        self.assertTrue(evaluate("a && b", {"a": True, "b": True}))
        self.assertFalse(evaluate("a && b", {"a": True}))
        self.assertTrue(evaluate("a || b", {"b": True}))
        self.assertTrue(evaluate("!a", {}))
        self.assertTrue(evaluate("", {}))

    def test_unknown_and_known_false(self):
        self.assertTrue(evaluate("unknown(children)", {}))
        self.assertFalse(evaluate("unknown(children)", {"children": False}))
        self.assertTrue(evaluate("children == false", {"children": False}))
        self.assertFalse(evaluate("children == false", {}))
        self.assertFalse(evaluate("children", {"children": "unknown"}))

    def test_compare_and_in(self):
        self.assertTrue(evaluate("channel != text", {"channel": "voice"}))
        self.assertFalse(evaluate("channel != text", {"channel": "text"}))
        self.assertTrue(evaluate("'book' in output_forms", {"output_forms": ["book", "comic"]}))
        self.assertFalse(evaluate("'book' in output_forms", {}))
        self.assertTrue(evaluate("(a || b) && !c", {"a": True}))

    def test_errors_and_no_eval(self):
        with self.assertRaises(ExprError):
            evaluate("a &&", {})
        with self.assertRaises(ExprError):
            evaluate("__import__('os').system('id')", {})
        with self.assertRaises(ExprError):
            evaluate("a; b", {})


class BankTests(unittest.TestCase):
    def setUp(self):
        self.bank = QuestionBank.from_file()

    def test_validate(self):
        self.assertEqual(self.bank.validate(), [])

    def test_count_in_range(self):
        self.assertGreaterEqual(len(self.bank.questions), 50)
        self.assertLessEqual(len(self.bank.questions), 120)

    def _walk(self, tags, settings=None, limit=300, auto_open_gates=True):
        profile = {"tags": tags, "settings": settings or {"order_mode": "chronological", "session_minutes": 30}}
        state, seen = fresh_state(), []
        for _ in range(limit):
            ctx = build_ctx(profile)
            nxt = self.bank.next(ctx, state, profile["settings"])
            if nxt["type"] == "gate":
                state["gates"][nxt["module"]["id"]] = "open" if auto_open_gates else "closed"
                continue
            if nxt["type"] != "question":
                break
            q = nxt["question"]
            seen.append(q["id"])
            record_answer(state, q["id"], "answered", q["sensitive"])
        return seen

    def test_children_branch(self):
        with_kids = self._walk({"children": True, "grandchildren": True, "siblings": True, "partner_now": True})
        no_kids = self._walk({"children": False, "siblings": False, "partner_ever": False})
        self.assertIn("k1", with_kids)
        self.assertNotIn("n1", with_kids)
        self.assertIn("n1", no_kids)
        self.assertNotIn("k1", no_kids)
        self.assertIn("c4", with_kids)
        self.assertIn("c4b", no_kids)
        self.assertNotIn("l1", no_kids)
        self.assertIn("l8", no_kids)

    def test_intro_first_and_unknowns_asked(self):
        seen = self._walk({})
        self.assertEqual(seen[0], "i1")
        self.assertIn("i5b", seen)  # дети неизвестны, значит спрашиваем
        self.assertIn("i5c", seen)

    def test_no_kid_question_when_unknown(self):
        seen = self._walk({})
        # без ответа про детей модуль kids/nokids не включается, но i5b про детей задаётся
        self.assertNotIn("k1", seen)

    def test_unknown_is_not_no(self):
        # пока ничего не известно, нельзя предполагать «нет детей / нет партнёра / не переезжал»
        seen = self._walk({})
        for qid in ("n1", "n2", "n3", "c4b", "l8", "e7"):
            self.assertNotIn(qid, seen)

    def test_gate_closed_skips_module(self):
        seen = self._walk({"children": False}, auto_open_gates=False)
        self.assertNotIn("d1", seen)
        self.assertNotIn("v1", seen)

    def test_avoid_modules(self):
        seen = self._walk({"children": True}, {"order_mode": "chronological", "session_minutes": 30, "avoid_modules": ["work", "military"]})
        self.assertFalse([q for q in seen if q.startswith("w")])

    def test_short_sessions_only_priority1(self):
        seen = self._walk({"children": True}, {"order_mode": "chronological", "session_minutes": 10})
        for qid in seen:
            self.assertEqual(self.bank.by_id[qid]["p"], 1 if qid not in ("i1",) else 1)

    def test_heavy_delay_for_listener(self):
        profile = {"tags": {"children": True}, "settings": {"role": "listener", "session_minutes": 30}}
        state = fresh_state()
        seen_gate = False
        for _ in range(300):
            nxt = self.bank.next(build_ctx(profile), state, profile["settings"])
            if nxt["type"] == "gate":
                seen_gate = True
                break
            if nxt["type"] != "question":
                break
            record_answer(state, nxt["question"]["id"], "answered", nxt["question"]["sensitive"])
        self.assertFalse(seen_gate, "для слушателя тяжёлые темы не должны предлагаться в первые 3 сессии")

    def test_by_theme_returns_choice(self):
        profile = {"tags": {"children": True}, "settings": {"order_mode": "by_theme", "session_minutes": 30}}
        state = fresh_state()
        # пройти знакомство
        for _ in range(30):
            nxt = self.bank.next(build_ctx(profile), state, profile["settings"])
            if nxt["type"] != "question":
                break
            record_answer(state, nxt["question"]["id"])
        self.assertEqual(nxt["type"], "choose_module")

    def test_partner_placeholder_fallback(self):
        ctx = build_ctx({"tags": {"partner_now": True}, "settings": {}})
        q = self.bank.by_id["l1"]
        from app.questions import fill_text
        self.assertNotIn("{partner}", fill_text(q["q"], ctx))
        ctx2 = build_ctx({"tags": {"partner_now": True, "partner_name": "Анной"}, "settings": {}})
        self.assertIn("Анной", fill_text(q["q"], ctx2))

    def test_war_childhood_derived_from_birth_year(self):
        self.assertTrue(build_ctx({"tags": {"birth_year": 1940}, "settings": {}})["war_childhood"])
        self.assertFalse(build_ctx({"tags": {"birth_year": 1975}, "settings": {}})["war_childhood"])


if __name__ == "__main__":
    unittest.main()
