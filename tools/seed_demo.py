#!/usr/bin/env python3
"""Создаёт демо-пользователя с несколькими рассказами (работает в mock-режиме).
Запуск из src/backend: DATA_DIR=../../data python3 ../../tools/seed_demo.py
Вход: demo@example.com / demo12345"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402

app = create_app(Config())
c = app.test_client()
r = c.post("/api/auth/register", json={"email": "demo@example.com", "password": "demo12345"})
if r.status_code == 409:
    r = c.post("/api/auth/login", json={"email": "demo@example.com", "password": "demo12345"})
h = {"Authorization": "Bearer " + r.get_json()["token"]}
c.put("/api/settings", headers=h, json={"settings": {"role": "companion", "preferred_name": "Анна", "session_minutes": 30,
      "output_forms": ["book", "timeline"]}, "onboarded": True})
sid = c.post("/api/session/start", headers=h).get_json()["session_id"]
stories = [
    ("c1", "Я выросла в маленьком доме у реки. В 1956 году мы переехали в город, и я пошла в первый класс."),
    ("s1", "Школа была большая, учительница Мария Ивановна учила нас петь. В 1962 году я окончила школу с медалью."),
    ("w1", "Первую работу я нашла в библиотеке. В 1965 году я начала работать библиотекарем и работала там тридцать лет."),
]
for qid, text in stories:
    c.post("/api/turn", headers=h, json={"session_id": sid, "question_id": qid, "text": text})
c.post("/api/timeline/refresh", headers=h)
c.post("/api/chapters/generate", headers=h, json={})
print("Готово. Вход: demo@example.com / demo12345")
