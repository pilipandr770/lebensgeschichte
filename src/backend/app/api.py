"""REST API. Все маршруты, кроме /health и /auth/*, требуют Bearer-токен."""
import json
import logging
import shutil

from flask import Blueprint, Response, current_app, g, jsonify, request

from . import db as dbmod
from . import exports
from .auth import require_auth
from .llm import clean_extraction
from .questions import NAME_KEYS, SENSITIVE_TAGS, TAG_KEYS, build_ctx, evaluate, record_answer
from .safety import detect_crisis
from .stt import clean_transcript, new_audio_name

log = logging.getLogger(__name__)
bp = Blueprint("api", __name__)

SETTING_KEYS = {
    "address_form", "preferred_name", "assistant_name", "role", "reaction_frequency", "pause_seconds", "tone",
    "humor", "sad_response", "avoid_modules", "clarify_mode", "verify_mode", "channel", "voice_speed",
    "session_minutes", "reminders", "schedule", "order_mode", "starter_photos", "output_forms", "text_style",
    "family_role", "trusted_contact", "session_end", "mood_goal", "auto_continue",
}


def svc():
    return current_app.extensions["services"]


def cfg():
    return current_app.config["CFG"]


def _rows(rows):
    return [dict(r) for r in rows]


# ---------- служебное ----------
@bp.get("/bootstrap")
@require_auth
def bootstrap():
    profile = dbmod.get_profile(g.user_id)
    ob = svc().onboarding
    modules = [{"id": m["id"], "title": m["title"]} for m in svc().bank.modules if m["id"] not in ("intro",)]
    questions = []
    for q in ob["stage_b_settings_questions"]:
        item = {k: v for k, v in q.items() if k != "options"}
        if q["key"] == "avoid_topics":
            item = {"id": q["id"], "key": "avoid_modules", "q": "Какие темы вы хотели бы пропускать? Можно ничего не выбирать.",
                    "multi": True, "optional": True,
                    "options": [{"label": m["title"], "value": m["id"]} for m in modules]}
        elif "options" in q:
            item["options"] = [{"label": k, "value": v} for k, v in q["options"].items()]
        questions.append(item)
    return jsonify(onboarded=profile["onboarded"], settings=profile["settings"],
                   intro_steps=ob["stage_a_intro_script"]["steps"], settings_questions=questions,
                   modules=modules, llm_provider=cfg().llm_provider, stt_provider=cfg().stt_provider)


@bp.put("/settings")
@require_auth
def put_settings():
    body = request.get_json(silent=True) or {}
    profile = dbmod.get_profile(g.user_id)
    incoming = {k: v for k, v in (body.get("settings") or {}).items() if k in SETTING_KEYS}
    settings = {**profile["settings"], **incoming}
    dbmod.save_profile(g.user_id, settings=settings, onboarded=body.get("onboarded"))
    return jsonify(settings=settings)


# ---------- сессии и вопросы ----------
def _next(profile):
    ctx = build_ctx(profile)
    return svc().bank.next(ctx, profile["state"], profile["settings"])


def _sessions_done(user_id):
    return dbmod.get_db().execute("SELECT COUNT(*) c FROM sessions WHERE user_id=? AND ended_at IS NOT NULL", (user_id,)).fetchone()["c"]


def _persist_next(user_id, profile):
    profile["state"]["sessions_done"] = _sessions_done(user_id)
    nxt = _next(profile)
    if nxt.get("bridge"):
        profile["state"]["last_sensitive"] = False  # мостик показан один раз
    dbmod.save_profile(user_id, state=profile["state"])
    return nxt


@bp.post("/session/start")
@require_auth
def session_start():
    db = dbmod.get_db()
    cur = db.execute("INSERT INTO sessions(user_id,started_at) VALUES(?,?)", (g.user_id, dbmod.now()))
    db.commit()
    profile = dbmod.get_profile(g.user_id)
    return jsonify(session_id=cur.lastrowid, next=_persist_next(g.user_id, profile))


@bp.get("/next")
@require_auth
def get_next():
    return jsonify(next=_persist_next(g.user_id, dbmod.get_profile(g.user_id)))


@bp.post("/gate")
@require_auth
def gate():
    body = request.get_json(silent=True) or {}
    mid = body.get("module_id")
    if mid not in svc().bank.mod_by_id:
        return jsonify(error="unknown_module"), 400
    profile = dbmod.get_profile(g.user_id)
    profile["state"]["gates"][mid] = "open" if body.get("open") else "closed"
    if body.get("open"):
        profile["state"]["current_module"] = mid
    dbmod.save_profile(g.user_id, state=profile["state"])
    return jsonify(next=_persist_next(g.user_id, profile))


@bp.post("/module")
@require_auth
def choose_module():
    body = request.get_json(silent=True) or {}
    mid = body.get("module_id")
    if mid not in svc().bank.mod_by_id:
        return jsonify(error="unknown_module"), 400
    profile = dbmod.get_profile(g.user_id)
    profile["state"]["current_module"] = mid
    dbmod.save_profile(g.user_id, state=profile["state"])
    return jsonify(next=_persist_next(g.user_id, profile))


@bp.post("/skip")
@require_auth
def skip():
    body = request.get_json(silent=True) or {}
    qid = body.get("question_id")
    profile = dbmod.get_profile(g.user_id)
    if qid in svc().bank.by_id:
        record_answer(profile["state"], qid, "skipped")
    offer_break = profile["state"].get("consecutive_skips", 0) >= 2
    if offer_break:
        profile["state"]["consecutive_skips"] = 0
        dbmod.save_profile(g.user_id, state=profile["state"])
        return jsonify(next={"type": "offer_break",
                             "text": "Давайте сменим тему или сделаем паузу. Как вам удобнее?"})
    return jsonify(next=_persist_next(g.user_id, profile))


def _reply_due(settings, turn_idx, words):
    role = settings.get("role", "listener")
    freq = settings.get("reaction_frequency", "sometimes")
    if role == "interviewer":
        return True
    every = {"often": 1, "sometimes": 2, "rare": 0}.get(freq, 2)
    if role == "listener":
        every = {"often": 2, "sometimes": 3, "rare": 0}.get(freq, 3)
    if every == 0:
        return words >= 80
    return turn_idx % every == 0


@bp.post("/turn")
@require_auth
def turn():
    uid = g.user_id
    profile = dbmod.get_profile(uid)
    form = request.form if request.form else (request.get_json(silent=True) or {})
    session_id = int(form.get("session_id") or 0) or None
    qid = form.get("question_id") or None
    q = svc().bank.by_id.get(qid) if qid else None
    cont = str(form.get("continue", "")).lower() in ("1", "true", "yes")

    transcript, audio_path = "", None
    f = request.files.get("audio")
    if f:
        name = new_audio_name(f.mimetype)
        user_dir = cfg().audio_dir / str(uid)
        user_dir.mkdir(parents=True, exist_ok=True)
        audio_path = user_dir / name
        f.save(audio_path)
        names = [profile["tags"].get("partner_name"), profile["tags"].get("birth_place")]
        prompt = ", ".join(n for n in names if n) or None
        try:
            transcript = clean_transcript(svc().stt.transcribe(audio_path, cfg().stt_language, prompt))
        except Exception:  # noqa: BLE001
            log.exception("STT failed")
            # Не 5xx: Cloudflare подменяет 502/504 своей страницей, и приложение не увидит причину.
            # Аудиофайл остаётся на диске, запись не теряется.
            return jsonify(status="stt_failed", error="stt_failed", transcript="", reply="")
        if not cfg().store_audio:
            audio_path.unlink(missing_ok=True)
            audio_path = None
    else:
        transcript = (form.get("text") or "").strip()

    if not transcript:
        return jsonify(status="empty", transcript="", reply="")

    db = dbmod.get_db()
    crisis = detect_crisis(transcript)
    cur = db.execute(
        "INSERT INTO recordings(user_id,session_id,question_id,module_id,audio_path,transcript,created_at,flagged_crisis) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (uid, session_id, qid, q["m"] if q else None, str(audio_path) if audio_path else None,
         transcript, dbmod.now(), 1 if crisis else 0))
    db.commit()
    rec_id = cur.lastrowid

    if crisis:
        return jsonify(status="crisis", crisis=True, transcript=transcript, recording_id=rec_id,
                       reply=cfg().crisis_text, next=None)

    warnings = []
    if q and not cont:
        record_answer(profile["state"], qid, "answered", sensitive=bool(q.get("sensitive")))

    # извлечение тегов
    if q and q.get("extract"):
        try:
            allowed = set(q["extract"])
            titles = {m["id"]: m["title"] for m in svc().bank.modules} if "avoid_modules" in allowed else None
            raw = svc().llm.extract_facts(transcript, allowed, titles)
            gate_open = profile["state"]["gates"].get(q["m"]) == "open"
            tags, names, avoid = clean_extraction(raw, allowed, gate_open, SENSITIVE_TAGS)
            profile["tags"].update(tags)
            profile["tags"].update(names)
            if avoid:
                valid = [m for m in avoid if m in svc().bank.mod_by_id and m != "intro"]
                profile["settings"]["avoid_modules"] = sorted(set(profile["settings"].get("avoid_modules", [])) | set(valid))
        except Exception:  # noqa: BLE001
            log.exception("extract failed")
            warnings.append("extract_failed")

    # реакция слушателя
    turn_idx = db.execute("SELECT COUNT(*) c FROM recordings WHERE user_id=? AND session_id IS ?", (uid, session_id)).fetchone()["c"]
    reply = ""
    if _reply_due(profile["settings"], turn_idx, len(transcript.split())):
        try:
            reply = svc().llm.listener_reply(profile["settings"], q["q"] if q else None, transcript)
        except Exception:  # noqa: BLE001
            log.exception("reply failed")
            warnings.append("reply_failed")

    dbmod.save_profile(uid, settings=profile["settings"], tags=profile["tags"], state=profile["state"])
    nxt = _persist_next(uid, dbmod.get_profile(uid))
    auto = profile["settings"].get("role") == "interviewer"
    return jsonify(status="ok", transcript=transcript, recording_id=rec_id, reply=reply, next=nxt,
                   auto_advance=auto, warnings=warnings)


@bp.post("/session/end")
@require_auth
def session_end():
    body = request.get_json(silent=True) or {}
    sid = body.get("session_id")
    db = dbmod.get_db()
    profile = dbmod.get_profile(g.user_id)
    recap = ""
    mode = profile["settings"].get("session_end", "recap")
    texts = [r["transcript"] for r in db.execute(
        "SELECT transcript FROM recordings WHERE user_id=? AND session_id IS ? AND flagged_crisis=0", (g.user_id, sid))]
    if texts and mode in ("warm", "recap"):
        try:
            recap = svc().llm.recap(profile["settings"], texts)
        except Exception:  # noqa: BLE001
            log.exception("recap failed")
    db.execute("UPDATE sessions SET ended_at=?, recap=? WHERE id=? AND user_id=?", (dbmod.now(), recap, sid, g.user_id))
    db.commit()
    return jsonify(recap=recap)


# ---------- записи ----------
@bp.get("/recordings")
@require_auth
def list_recordings():
    rows = dbmod.get_db().execute(
        "SELECT id,session_id,question_id,module_id,transcript,created_at FROM recordings "
        "WHERE user_id=? AND flagged_crisis=0 ORDER BY id", (g.user_id,))
    return jsonify(recordings=_rows(rows))


@bp.patch("/recordings/<int:rid>")
@require_auth
def patch_recording(rid):
    body = request.get_json(silent=True) or {}
    text = (body.get("transcript") or "").strip()
    if not text:
        return jsonify(error="empty"), 400
    db = dbmod.get_db()
    db.execute("UPDATE recordings SET transcript=?, events_done=0 WHERE id=? AND user_id=?", (text, rid, g.user_id))
    db.commit()
    return jsonify(ok=True)


# ---------- дорога жизни ----------
def _event_row(r):
    d = dict(r)
    d["people"] = json.loads(d.pop("people_json") or "[]")
    return d


@bp.get("/timeline")
@require_auth
def timeline():
    rows = dbmod.get_db().execute(
        "SELECT * FROM events WHERE user_id=? ORDER BY year IS NULL, year, id", (g.user_id,))
    return jsonify(events=[_event_row(r) for r in rows])


@bp.post("/timeline/refresh")
@require_auth
def timeline_refresh():
    db = dbmod.get_db()
    recs = db.execute("SELECT id,transcript FROM recordings WHERE user_id=? AND events_done=0 AND flagged_crisis=0", (g.user_id,)).fetchall()
    existing = {((r["title"] or "").lower(), r["year"]) for r in db.execute("SELECT title,year FROM events WHERE user_id=?", (g.user_id,))}
    added = 0
    for r in recs:
        if len(r["transcript"]) >= 40:
            try:
                events = svc().llm.extract_events(r["transcript"])
            except Exception:  # noqa: BLE001
                log.exception("events failed")
                continue
            for e in events:
                title = (e.get("title") or "").strip()
                year = e.get("year") if isinstance(e.get("year"), int) else None
                if not title or (title.lower(), year) in existing:
                    continue
                db.execute("INSERT INTO events(user_id,recording_id,title,year,date_text,place,people_json,summary,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (g.user_id, r["id"], title, year, e.get("date_text"), e.get("place"),
                            json.dumps(e.get("people") or [], ensure_ascii=False), e.get("summary"), dbmod.now()))
                existing.add((title.lower(), year))
                added += 1
        db.execute("UPDATE recordings SET events_done=1 WHERE id=?", (r["id"],))
    db.commit()
    return jsonify(added=added)


@bp.patch("/timeline/<int:eid>")
@require_auth
def patch_event(eid):
    body = request.get_json(silent=True) or {}
    fields, vals = [], []
    for key in ("title", "summary", "place", "date_text"):
        if key in body:
            fields.append(f"{key}=?")
            vals.append(body[key])
    if "year" in body:
        fields.append("year=?")
        vals.append(body["year"] if isinstance(body["year"], int) else None)
    if "confirmed" in body:
        fields.append("confirmed=?")
        vals.append(1 if body["confirmed"] else 0)
    if not fields:
        return jsonify(error="nothing_to_update"), 400
    db = dbmod.get_db()
    db.execute(f"UPDATE events SET {', '.join(fields)} WHERE id=? AND user_id=?", (*vals, eid, g.user_id))
    db.commit()
    return jsonify(ok=True)


@bp.delete("/timeline/<int:eid>")
@require_auth
def delete_event(eid):
    db = dbmod.get_db()
    db.execute("DELETE FROM events WHERE id=? AND user_id=?", (eid, g.user_id))
    db.commit()
    return jsonify(ok=True)


# ---------- книга и комикс ----------
def _chapter_row(r):
    d = dict(r)
    d["comic"] = json.loads(d.pop("comic_json")) if d.get("comic_json") else None
    return d


@bp.get("/chapters")
@require_auth
def chapters():
    rows = dbmod.get_db().execute("SELECT * FROM chapters WHERE user_id=? ORDER BY id", (g.user_id,))
    return jsonify(chapters=[_chapter_row(r) for r in rows])


@bp.post("/chapters/generate")
@require_auth
def chapters_generate():
    body = request.get_json(silent=True) or {}
    only = body.get("module_id")
    force = bool(body.get("force"))
    db = dbmod.get_db()
    profile = dbmod.get_profile(g.user_id)
    bank = svc().bank
    mods = [m for m in bank.modules if (not only or m["id"] == only)]
    made = []
    for m in mods:
        rows = db.execute("SELECT question_id, transcript FROM recordings WHERE user_id=? AND module_id=? AND flagged_crisis=0 ORDER BY id",
                          (g.user_id, m["id"])).fetchall()
        if not rows:
            continue
        existing = db.execute("SELECT * FROM chapters WHERE user_id=? AND module_id=?", (g.user_id, m["id"])).fetchone()
        if existing and existing["status"] == "confirmed" and not force:
            continue
        pairs = [((bank.by_id.get(r["question_id"]) or {}).get("q", ""), r["transcript"]) for r in rows]
        try:
            text = svc().llm.write_chapter(profile["settings"], m["title"], pairs)
        except Exception:  # noqa: BLE001
            log.exception("chapter failed")
            continue
        if existing:
            db.execute("UPDATE chapters SET body=?, status='draft', comic_json=NULL, updated_at=? WHERE id=?", (text, dbmod.now(), existing["id"]))
        else:
            db.execute("INSERT INTO chapters(user_id,module_id,title,body,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                       (g.user_id, m["id"], m["title"], text, "draft", dbmod.now(), dbmod.now()))
        made.append(m["id"])
    db.commit()
    return jsonify(generated=made)


@bp.patch("/chapters/<int:cid>")
@require_auth
def patch_chapter(cid):
    body = request.get_json(silent=True) or {}
    fields, vals = [], []
    for key in ("title", "body", "status"):
        if key in body:
            if key == "status" and body[key] not in ("draft", "confirmed"):
                return jsonify(error="bad_status"), 400
            fields.append(f"{key}=?")
            vals.append(body[key])
    if not fields:
        return jsonify(error="nothing_to_update"), 400
    fields.append("updated_at=?")
    vals.append(dbmod.now())
    db = dbmod.get_db()
    db.execute(f"UPDATE chapters SET {', '.join(fields)} WHERE id=? AND user_id=?", (*vals, cid, g.user_id))
    db.commit()
    return jsonify(ok=True)


@bp.post("/chapters/<int:cid>/comic")
@require_auth
def chapter_comic(cid):
    db = dbmod.get_db()
    row = db.execute("SELECT * FROM chapters WHERE id=? AND user_id=?", (cid, g.user_id)).fetchone()
    if row is None:
        return jsonify(error="not_found"), 404
    try:
        scenes = svc().llm.comic_scenes(row["body"])
    except Exception:  # noqa: BLE001
        log.exception("comic failed")
        return jsonify(error="llm_failed"), 502
    db.execute("UPDATE chapters SET comic_json=? WHERE id=?", (json.dumps(scenes, ensure_ascii=False), cid))
    db.commit()
    return jsonify(scenes=scenes)


def _book_data():
    profile = dbmod.get_profile(g.user_id)
    rows = dbmod.get_db().execute("SELECT title, body FROM chapters WHERE user_id=? ORDER BY id", (g.user_id,))
    return profile["settings"], [dict(r) for r in rows]


@bp.get("/export/book.<fmt>")
@require_auth
def export_book(fmt):
    settings, chs = _book_data()
    if fmt == "md":
        return Response(exports.book_markdown(settings, chs), mimetype="text/markdown",
                        headers={"Content-Disposition": "attachment; filename=lebensgeschichte.md"})
    if fmt == "html":
        return Response(exports.book_html(settings, chs), mimetype="text/html",
                        headers={"Content-Disposition": "attachment; filename=lebensgeschichte.html"})
    if fmt == "pdf":
        try:
            data = exports.book_pdf(settings, chs)
        except RuntimeError as e:
            return jsonify(error="pdf_unavailable", detail=str(e)), 501
        return Response(data, mimetype="application/pdf",
                        headers={"Content-Disposition": "attachment; filename=lebensgeschichte.pdf"})
    return jsonify(error="unknown_format"), 404


# ---------- данные пользователя (DSGVO: переносимость и удаление) ----------
@bp.get("/export/data.zip")
@require_auth
def export_data():
    db = dbmod.get_db()
    profile = dbmod.get_profile(g.user_id)
    recs = _rows(db.execute("SELECT id,session_id,question_id,module_id,audio_path,transcript,created_at FROM recordings WHERE user_id=?", (g.user_id,)))
    events = [_event_row(r) for r in db.execute("SELECT * FROM events WHERE user_id=?", (g.user_id,))]
    chs = [_chapter_row(r) for r in db.execute("SELECT * FROM chapters WHERE user_id=?", (g.user_id,))]
    data = exports.data_zip({"settings": profile["settings"], "tags": profile["tags"]}, recs, events, chs, cfg().audio_dir)
    return Response(data, mimetype="application/zip", headers={"Content-Disposition": "attachment; filename=meine-daten.zip"})


@bp.delete("/me")
@require_auth
def delete_me():
    uid = g.user_id
    shutil.rmtree(cfg().audio_dir / str(uid), ignore_errors=True)
    db = dbmod.get_db()
    db.execute("DELETE FROM users WHERE id=?", (uid,))  # каскадно удаляет профиль, записи, события, главы
    db.commit()
    return jsonify(ok=True)
