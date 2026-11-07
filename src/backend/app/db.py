"""SQLite-слой. Для продакшена с несколькими воркерами заменить на Postgres (см. docs/05-deployment.md)."""
import json
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles(
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  settings_json TEXT NOT NULL DEFAULT '{}',
  tags_json TEXT NOT NULL DEFAULT '{}',
  state_json TEXT NOT NULL DEFAULT '{}',
  onboarded INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  recap TEXT
);
CREATE TABLE IF NOT EXISTS recordings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  session_id INTEGER,
  question_id TEXT,
  module_id TEXT,
  audio_path TEXT,
  transcript TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  events_done INTEGER NOT NULL DEFAULT 0,
  flagged_crisis INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  recording_id INTEGER,
  title TEXT NOT NULL,
  year INTEGER,
  date_text TEXT,
  place TEXT,
  people_json TEXT NOT NULL DEFAULT '[]',
  summary TEXT,
  confirmed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  module_id TEXT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  comic_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rec_user ON recordings(user_id);
CREATE INDEX IF NOT EXISTS idx_evt_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_ch_user ON chapters(user_id);
"""

DEFAULT_STATE = {"asked": {}, "gates": {}, "consecutive_skips": 0,
                 "last_sensitive": False, "bridge_idx": 0, "current_module": None}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["CFG"].db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def get_profile(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        db.execute("INSERT INTO profiles(user_id) VALUES(?)", (user_id,))
        db.commit()
        row = db.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    state = json.loads(row["state_json"] or "{}")
    for k, v in DEFAULT_STATE.items():
        state.setdefault(k, json.loads(json.dumps(v)))
    return {"settings": json.loads(row["settings_json"] or "{}"),
            "tags": json.loads(row["tags_json"] or "{}"),
            "state": state, "onboarded": bool(row["onboarded"])}


def save_profile(user_id, settings=None, tags=None, state=None, onboarded=None):
    db = get_db()
    get_profile(user_id)
    if settings is not None:
        db.execute("UPDATE profiles SET settings_json=? WHERE user_id=?", (json.dumps(settings, ensure_ascii=False), user_id))
    if tags is not None:
        db.execute("UPDATE profiles SET tags_json=? WHERE user_id=?", (json.dumps(tags, ensure_ascii=False), user_id))
    if state is not None:
        db.execute("UPDATE profiles SET state_json=? WHERE user_id=?", (json.dumps(state, ensure_ascii=False), user_id))
    if onboarded is not None:
        db.execute("UPDATE profiles SET onboarded=? WHERE user_id=?", (1 if onboarded else 0, user_id))
    db.commit()
