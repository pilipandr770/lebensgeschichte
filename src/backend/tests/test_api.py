import io
import tempfile
import unittest
import zipfile

from app import create_app
from app.config import Config


def make_client():
    tmp = tempfile.TemporaryDirectory()
    cfg = Config({"DATA_DIR": tmp.name, "SECRET_KEY": "test", "LLM_PROVIDER": "mock", "STT_PROVIDER": "mock"})
    app = create_app(cfg)
    return tmp, app, app.test_client()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.app, self.c = make_client()
        r = self.c.post("/api/auth/register", json={"email": "oma@example.com", "password": "secret123"})
        self.assertEqual(r.status_code, 201)
        self.h = {"Authorization": "Bearer " + r.get_json()["token"]}

    def tearDown(self):
        self.tmp.cleanup()

    def j(self, method, url, **kw):
        kw.setdefault("headers", self.h)
        return getattr(self.c, method)(url, **kw)

    def test_health_and_auth(self):
        self.assertEqual(self.c.get("/health").get_json()["status"], "ok")
        self.assertEqual(self.c.get("/api/bootstrap").status_code, 401)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "oma@example.com", "password": "wrong"}).status_code, 401)
        self.assertEqual(self.c.post("/api/auth/login", json={"email": "oma@example.com", "password": "secret123"}).status_code, 200)
        self.assertEqual(self.c.post("/api/auth/register", json={"email": "oma@example.com", "password": "secret123"}).status_code, 409)
        self.assertEqual(self.c.post("/api/auth/register", json={"email": "x@y.de", "password": "short"}).status_code, 400)

    def test_bootstrap_and_settings(self):
        b = self.j("get", "/api/bootstrap").get_json()
        self.assertFalse(b["onboarded"])
        self.assertTrue(b["intro_steps"])
        keys = [q["key"] for q in b["settings_questions"]]
        self.assertIn("role", keys)
        self.assertIn("avoid_modules", keys)
        r = self.j("put", "/api/settings", json={"settings": {"role": "listener", "preferred_name": "Анна", "evil": 1}, "onboarded": True})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("evil", r.get_json()["settings"])
        self.assertTrue(self.j("get", "/api/bootstrap").get_json()["onboarded"])

    def test_full_flow(self):
        self.j("put", "/api/settings", json={"settings": {"role": "interviewer", "session_minutes": 30, "preferred_name": "Анна"}, "onboarded": True})
        s = self.j("post", "/api/session/start").get_json()
        sid, nxt = s["session_id"], s["next"]
        self.assertEqual(nxt["question"]["id"], "i1")
        # ответ на вопрос о детях через текст, чтобы mock-экстрактор поставил children
        guard = 0
        while nxt["type"] == "question" and nxt["question"]["id"] != "i5" and guard < 10:
            r = self.j("post", "/api/turn", json={"session_id": sid, "question_id": nxt["question"]["id"], "text": "Меня зовут Анна, я родилась в 1948 году."}).get_json()
            nxt = r["next"]
            guard += 1
        self.assertEqual(nxt["question"]["id"], "i5")
        r = self.j("post", "/api/turn", json={"session_id": sid, "question_id": "i5", "text": "У меня двое детей и внуки, есть собака."}).get_json()
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["reply"])  # interviewer отвечает каждый раз
        self.assertTrue(r["auto_advance"])
        # i5b про детей не должен задаваться, т.к. дети уже известны
        self.assertNotEqual(r["next"]["question"]["id"], "i5b")

    def test_stt_failure_is_not_5xx_and_keeps_audio(self):
        class Boom:
            def transcribe(self, *a, **k):
                raise RuntimeError("quota")
        self.app.extensions["services"].stt = Boom()
        s = self.j("post", "/api/session/start").get_json()
        data = {"session_id": str(s["session_id"]), "question_id": "i1", "audio": (io.BytesIO(b"fake-audio"), "a.webm", "audio/webm")}
        r = self.j("post", "/api/turn", data=data, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)  # не 5xx: Cloudflare подменяет 502/504 своей страницей
        self.assertEqual(r.get_json()["status"], "stt_failed")
        files = list((self.app.config["CFG"].audio_dir).rglob("*.webm"))
        self.assertEqual(len(files), 1)  # запись не теряется

    def test_whisper_hallucination_is_dropped(self):
        from app.stt import clean_transcript
        self.assertEqual(clean_transcript("Редактор субтитров А.Синецкая Корректор А.Егорова"), "")
        self.assertEqual(clean_transcript("Продолжение следует..."), "")
        self.assertEqual(clean_transcript("Untertitel im Auftrag des ZDF, 2020"), "")
        real = "Мы жили у реки, а бабушка была корректором в местной газете."
        self.assertEqual(clean_transcript(real), real)
        self.assertEqual(clean_transcript("  "), "")

    def test_audio_upload_mock_stt(self):
        s = self.j("post", "/api/session/start").get_json()
        data = {"session_id": str(s["session_id"]), "question_id": "i1", "audio": (io.BytesIO(b"fake-audio"), "a.webm", "audio/webm")}
        r = self.c.post("/api/turn", data=data, headers=self.h, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertIn("mock", r.get_json()["transcript"])

    def test_crisis_path(self):
        s = self.j("post", "/api/session/start").get_json()
        r = self.j("post", "/api/turn", json={"session_id": s["session_id"], "question_id": "i1", "text": "Иногда мне кажется, я не хочу жить."}).get_json()
        self.assertTrue(r["crisis"])
        self.assertIn("112", r["reply"])
        self.assertIsNone(r["next"])
        # кризисная запись не попадает в список записей и в книгу
        self.assertEqual(self.j("get", "/api/recordings").get_json()["recordings"], [])

    def test_timeline_chapters_exports(self):
        s = self.j("post", "/api/session/start").get_json()
        self.j("post", "/api/turn", json={"session_id": s["session_id"], "question_id": "c1",
               "text": "Я вырос в маленьком доме у реки. В 1956 году мы переехали в город, и я пошёл в школу."})
        self.assertEqual(self.j("post", "/api/timeline/refresh").get_json()["added"], 1)
        ev = self.j("get", "/api/timeline").get_json()["events"]
        self.assertEqual(ev[0]["year"], 1956)
        self.assertEqual(self.j("patch", f"/api/timeline/{ev[0]['id']}", json={"confirmed": True}).status_code, 200)
        self.assertEqual(self.j("post", "/api/timeline/refresh").get_json()["added"], 0)

        g = self.j("post", "/api/chapters/generate", json={}).get_json()
        self.assertEqual(g["generated"], ["childhood"])
        chs = self.j("get", "/api/chapters").get_json()["chapters"]
        self.assertEqual(len(chs), 1)
        cid = chs[0]["id"]
        self.assertEqual(self.j("patch", f"/api/chapters/{cid}", json={"status": "confirmed"}).status_code, 200)
        self.assertEqual(self.j("patch", f"/api/chapters/{cid}", json={"status": "bogus"}).status_code, 400)
        # подтверждённая глава не перезаписывается
        self.assertEqual(self.j("post", "/api/chapters/generate", json={}).get_json()["generated"], [])
        sc = self.j("post", f"/api/chapters/{cid}/comic").get_json()["scenes"]
        self.assertTrue(sc)

        md = self.j("get", "/api/export/book.md")
        self.assertEqual(md.status_code, 200)
        self.assertIn("## Детство", md.get_data(as_text=True))
        self.assertIn("<h2>", self.j("get", "/api/export/book.html").get_data(as_text=True))
        self.assertIn(self.j("get", "/api/export/book.pdf").status_code, (200, 501))

        z = self.j("get", "/api/export/data.zip")
        names = zipfile.ZipFile(io.BytesIO(z.data)).namelist()
        self.assertIn("transcripts.json", names)

    def test_gate_and_skip(self):
        self.j("put", "/api/settings", json={"settings": {"role": "companion", "session_minutes": 30, "sad_response": "support"}})
        s = self.j("post", "/api/session/start").get_json()
        r = self.j("post", "/api/skip", json={"question_id": "i1"}).get_json()
        r = self.j("post", "/api/skip", json={"question_id": "i2"}).get_json()
        self.assertEqual(r["next"]["type"], "offer_break")
        self.assertEqual(self.j("post", "/api/gate", json={"module_id": "nope", "open": True}).status_code, 400)

    def test_delete_me(self):
        self.j("post", "/api/session/start")
        self.assertEqual(self.j("delete", "/api/me").status_code, 200)
        self.assertEqual(self.j("get", "/api/bootstrap").status_code, 401)

    def test_user_isolation(self):
        r2 = self.c.post("/api/auth/register", json={"email": "opa@example.com", "password": "secret123"})
        h2 = {"Authorization": "Bearer " + r2.get_json()["token"]}
        s = self.j("post", "/api/session/start").get_json()
        self.j("post", "/api/turn", json={"session_id": s["session_id"], "question_id": "c1", "text": "Я часто вспоминаю детство. В 1950 году я родился в маленькой деревне."})
        self.j("post", "/api/timeline/refresh")
        self.assertEqual(self.c.get("/api/timeline", headers=h2).get_json()["events"], [])
        ev = self.j("get", "/api/timeline").get_json()["events"]
        self.c.delete(f"/api/timeline/{ev[0]['id']}", headers=h2)  # чужое удаление не должно сработать
        self.assertEqual(len(self.j("get", "/api/timeline").get_json()["events"]), 1)


if __name__ == "__main__":
    unittest.main()
