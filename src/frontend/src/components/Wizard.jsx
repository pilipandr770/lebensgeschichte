import React, { useMemo, useState } from "react";
import { api } from "../api.js";
import { evalIf } from "../evalIf.js";

// Этап B: настройка правил поведения. Один вопрос на экран, крупные кнопки.
export default function Wizard({ questions, initial, onDone }) {
  const [answers, setAnswers] = useState(initial || {});
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const visible = useMemo(() => questions.filter((q) => evalIf(q.if, answers)), [questions, answers]);
  const q = visible[Math.min(idx, visible.length - 1)];
  const last = idx >= visible.length - 1;

  const set = (key, value) => setAnswers((a) => ({ ...a, [key]: value }));

  async function finish(finalAnswers) {
    setBusy(true);
    setError("");
    try {
      await api.put("/settings", { settings: finalAnswers, onboarded: true });
      onDone(finalAnswers);
    } catch (e) {
      setError("Не удалось сохранить настройки. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  function advance(updated = answers) {
    if (last) finish(updated);
    else setIdx(idx + 1);
  }

  function choose(value) {
    const updated = { ...answers, [q.key]: value };
    setAnswers(updated);
    if (!q.also_collect) advance(updated);
  }

  function toggle(value) {
    const cur = Array.isArray(answers[q.key]) ? answers[q.key] : [];
    set(q.key, cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value]);
  }

  if (!q) return null;
  const selected = answers[q.key];

  return (
    <main className="card">
      <p className="muted">Настройка · {Math.min(idx + 1, visible.length)} из {visible.length}</p>
      <h2 className="big-text">{q.q}</h2>

      {q.options && !q.multi && (
        <div className="stack">
          {q.options.map((o) => (
            <button key={String(o.value)} className={"big" + (selected === o.value ? " primary" : "")} onClick={() => choose(o.value)}>
              {o.label}
            </button>
          ))}
        </div>
      )}

      {q.options && q.multi && (
        <div className="stack">
          {q.options.map((o) => {
            const on = Array.isArray(selected) && selected.includes(o.value);
            return (
              <button key={o.value} className={"big" + (on ? " primary" : "")} onClick={() => toggle(o.value)}>
                {on ? "✓ " : ""}{o.label}
              </button>
            );
          })}
        </div>
      )}

      {q.free_text && (
        <textarea rows={4} value={answers[q.key] || ""} onChange={(e) => set(q.key, e.target.value)}
                  placeholder="Можно написать своими словами или пропустить" />
      )}

      {q.also_collect && (
        <label>
          {q.also_collect === "preferred_name" ? "Как вас называть?" : "Когда удобно? (дни и время)"}
          <input value={answers[q.also_collect] || ""} onChange={(e) => set(q.also_collect, e.target.value)} />
        </label>
      )}

      {error && <p className="error">{error}</p>}

      <div className="row">
        {idx > 0 && <button className="big" onClick={() => setIdx(idx - 1)}>Назад</button>}
        {(q.multi || q.free_text || q.also_collect || q.optional) && (
          <button className="big primary" disabled={busy} onClick={() => advance()}>
            {last ? "Готово" : q.optional && !answers[q.key] ? "Пропустить" : "Дальше"}
          </button>
        )}
      </div>
    </main>
  );
}
