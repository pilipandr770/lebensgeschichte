import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { cancelSpeech, guessLang, speak } from "../tts.js";
import { useRecorder } from "../useRecorder.js";

// Режим «пошагово»: одна кнопка «Рассказать», остановка по паузе, ответ озвучивается сам.
export default function Talk({ settings }) {
  const channel = settings.channel || "voice";
  const voiceOn = channel !== "text";
  const textOn = channel !== "voice";
  const slow = settings.voice_speed === "slow";
  const pause = Number(settings.pause_seconds) || 4;

  const [sessionId, setSessionId] = useState(null);
  const [next, setNext] = useState(null);
  const [phase, setPhase] = useState("loading"); // loading | ready | recording | sending | reacted | ended
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [crisis, setCrisis] = useState(false);
  const [recap, setRecap] = useState("");
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const answered = useRef(null); // вопрос, на который только что ответили
  const cont = useRef(false); // «рассказать ещё» к тому же вопросу
  const sessionRef = useRef(null);
  const lastBlob = useRef(null); // последняя запись, которую не удалось распознать

  const say = useCallback(
    (t) => (voiceOn && t ? speak(t, { lang: guessLang(t), slow }) : Promise.resolve()),
    [voiceOn, slow]
  );

  const presentNext = useCallback(
    async (nxt, lead) => {
      cancelSpeech();
      setNext(nxt);
      setPhase("ready");
      if (lead) await say(lead);
      if (nxt?.type === "question") {
        if (nxt.bridge) await say(nxt.bridge);
        await say(nxt.question.text);
        if (settings.auto_continue && voiceOn) recorder.start();
      } else if (nxt?.type === "gate") await say(nxt.text);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [say, settings.auto_continue, voiceOn]
  );

  const send = useCallback(
    async (blob, typed) => {
      const q = cont.current ? answered.current : next?.type === "question" ? next.question : null;
      if (!blob && !typed) {
        setNote("Я ничего не услышал. Нажмите «Рассказать» и попробуйте ещё раз.");
        setPhase("ready");
        return;
      }
      setPhase("sending");
      setNote("");
      setError("");
      try {
        const form = new FormData();
        if (blob) form.append("audio", blob, "recording." + (blob.type.includes("mp4") ? "m4a" : "webm"));
        if (typed) form.append("text", typed);
        form.append("session_id", sessionRef.current);
        if (q) form.append("question_id", q.id);
        if (cont.current) form.append("continue", "1");
        const r = await api.postForm("/turn", form);
        if (r.status === "stt_failed") {
          // запись не теряем: человек может отправить её ещё раз или написать текстом
          lastBlob.current = blob || null;
          setError(
            blob
              ? "Не получилось распознать речь. Ваша запись не потеряна: нажмите «Отправить запись ещё раз»" +
                (textOn ? " или напишите текстом." : ".")
              : "Не получилось обработать текст. Попробуйте ещё раз."
          );
          setPhase("ready");
          return;
        }
        lastBlob.current = null;
        setText("");
        if (r.status === "empty") {
          setNote("Я не смог разобрать запись. Попробуйте ещё раз.");
          setPhase("ready");
          return;
        }
        setTranscript(r.transcript);
        setReply(r.reply || "");
        if (r.crisis) {
          setCrisis(true);
          setPhase("reacted");
          await say(r.reply);
          return;
        }
        if (q && !cont.current) answered.current = q;
        cont.current = false;
        if (r.auto_advance) {
          setPhase("reacted");
          await presentNext(r.next, r.reply);
        } else {
          setNext(r.next);
          setPhase("reacted");
          await say(r.reply);
        }
      } catch (e) {
        setError(e.message === "stt_failed" ? "Не удалось распознать речь. Попробуйте ещё раз." : "Что-то пошло не так. Попробуйте ещё раз.");
        setPhase("ready");
      }
    },
    [next, presentNext, say]
  );

  const recorder = useRecorder({ pauseSeconds: pause, onFinish: (blob) => send(blob, null) });

  useEffect(() => {
    api.post("/session/start").then((r) => {
      setSessionId(r.session_id);
      sessionRef.current = r.session_id;
      presentNext(r.next);
    }).catch(() => setError("Не удалось начать разговор."));
    return () => cancelSpeech();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (recorder.state === "recording") setPhase("recording");
  }, [recorder.state]);

  const act = async (fn) => {
    cancelSpeech();
    lastBlob.current = null;
    setError("");
    try {
      const r = await fn();
      setCrisis(false);
      setReply("");
      await presentNext(r.next);
    } catch (e) {
      setError("Не получилось. Попробуйте ещё раз.");
    }
  };

  async function endSession() {
    cancelSpeech();
    recorder.state === "recording" && recorder.stop();
    try {
      const r = await api.post("/session/end", { session_id: sessionId });
      setRecap(r.recap || "");
      setPhase("ended");
      await say(r.recap);
    } catch (e) {
      setPhase("ended");
    }
  }

  function tellMore() {
    cancelSpeech();
    cont.current = true;
    setCrisis(false);
    setPhase("ready");
    if (voiceOn) recorder.start();
  }

  function goNext() {
    cancelSpeech();
    cont.current = false;
    setCrisis(false);
    presentNext(next);
  }

  if (phase === "loading") return <main className="card"><p className="lead">Минутку…</p></main>;

  if (phase === "ended")
    return (
      <main className="card">
        <h2>Спасибо!</h2>
        {recap && <p className="lead">{recap}</p>}
        <p>Ваши рассказы сохранены. Загляните в «Дорогу жизни» и «Книгу».</p>
      </main>
    );

  const q = next?.type === "question" ? next.question : null;
  const showQuestion = phase === "ready" || phase === "recording";

  return (
    <main className="card">
      {crisis && <div className="crisis" role="alert"><p>{reply}</p></div>}

      {phase === "reacted" && !crisis && (
        <div className="reaction">
          {transcript && <p className="muted transcript">«{transcript}»</p>}
          {reply && <p className="lead">{reply}</p>}
          <div className="row">
            <button className="big" onClick={tellMore}>Рассказать ещё</button>
            <button className="big primary" onClick={goNext}>Дальше</button>
          </div>
        </div>
      )}

      {phase === "reacted" && crisis && (
        <div className="row">
          <button className="big" onClick={tellMore}>Продолжить запись</button>
          <button className="big primary" onClick={endSession}>Сделать паузу на сегодня</button>
        </div>
      )}

      {showQuestion && next?.type === "question" && (
        <>
          <p className="muted">{q.module_title}</p>
          {next.bridge && <p className="muted">{next.bridge}</p>}
          <h2 className="big-text">{q.text}</h2>
          {q.sensitive && <p className="muted">Если не хочется отвечать, просто нажмите «Пропустить».</p>}
        </>
      )}

      {showQuestion && next?.type === "gate" && (
        <>
          <h2 className="big-text">{next.text}</h2>
          <div className="row">
            <button className="big primary" onClick={() => act(() => api.post("/gate", { module_id: next.module.id, open: true }))}>Да, давайте</button>
            <button className="big" onClick={() => act(() => api.post("/gate", { module_id: next.module.id, open: false }))}>Не сейчас</button>
          </div>
        </>
      )}

      {showQuestion && next?.type === "choose_module" && (
        <>
          <h2 className="big-text">О чём хотите рассказать сегодня?</h2>
          <div className="stack">
            {next.modules.map((m) => (
              <button key={m.id} className="big" onClick={() => act(() => api.post("/module", { module_id: m.id }))}>{m.title}</button>
            ))}
          </div>
        </>
      )}

      {showQuestion && next?.type === "offer_break" && (
        <>
          <h2 className="big-text">{next.text}</h2>
          <div className="row">
            <button className="big primary" onClick={() => act(() => api.get("/next"))}>Продолжим</button>
            <button className="big" onClick={endSession}>Закончить на сегодня</button>
          </div>
        </>
      )}

      {showQuestion && next?.type === "done" && (
        <>
          <h2 className="big-text">На сегодня вопросы закончились. Вы рассказали очень много!</h2>
          <button className="big primary" onClick={endSession}>Завершить</button>
        </>
      )}

      {showQuestion && q && (
        <>
          {voiceOn && phase === "ready" && (
            <button className="record" onClick={() => { cancelSpeech(); cont.current = false; recorder.start(); }}>Рассказать</button>
          )}
          {phase === "recording" && (
            <div className="listening" aria-live="polite">
              <div className="pulse" style={{ transform: `scale(${1 + recorder.level * 0.6})` }} />
              <p className="lead">Я вас слушаю…</p>
              <button className="big primary" onClick={recorder.stop}>Закончить</button>
            </div>
          )}
          {phase === "ready" && lastBlob.current && (
            <button className="big primary" onClick={() => send(lastBlob.current, null)}>Отправить запись ещё раз</button>
          )}
          {textOn && phase === "ready" && (
            <div className="textmode">
              <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Или напишите здесь" />
              <button className="big" disabled={!text.trim()} onClick={() => send(null, text.trim())}>Отправить</button>
            </div>
          )}
          {phase === "ready" && (
            <div className="row small-row">
              <button className="link" onClick={() => act(() => api.post("/skip", { question_id: q.id }))}>Пропустить</button>
              <button className="link" onClick={endSession}>Закончить на сегодня</button>
            </div>
          )}
        </>
      )}

      {phase === "sending" && <p className="lead">Слушаю запись…</p>}
      {note && <p className="muted">{note}</p>}
      {(error || recorder.error) && <p className="error">{error || recorder.error}</p>}
    </main>
  );
}
