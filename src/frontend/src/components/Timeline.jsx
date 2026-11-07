import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

// «Дорога жизни»: события из рассказов на дороге. Человек подтверждает или удаляет, чтобы ИИ ничего не выдумал.
export default function Timeline() {
  const [events, setEvents] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => api.get("/timeline").then((r) => setEvents(r.events)), []);
  useEffect(() => { load(); }, [load]);

  async function refresh() {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.post("/timeline/refresh");
      setMsg(r.added ? `Добавлено событий: ${r.added}` : "Новых событий пока нет.");
      await load();
    } catch (e) {
      setMsg("Не получилось обновить. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e) {
    await api.patch(`/timeline/${e.id}`, { confirmed: !e.confirmed });
    load();
  }

  async function remove(e) {
    if (!window.confirm("Убрать это событие с дороги?")) return;
    await api.del(`/timeline/${e.id}`);
    load();
  }

  async function edit(e) {
    const title = window.prompt("Название события", e.title);
    if (title === null || !title.trim()) return;
    await api.patch(`/timeline/${e.id}`, { title: title.trim() });
    load();
  }

  return (
    <main className="card wide">
      <h2>Дорога жизни</h2>
      <button className="big" disabled={busy} onClick={refresh}>{busy ? "Ищу события…" : "Собрать события из рассказов"}</button>
      {msg && <p className="muted">{msg}</p>}
      {events && events.length === 0 && <p className="lead">Пока здесь пусто. Расскажите что-нибудь, и события появятся на дороге.</p>}
      <ol className="road">
        {(events || []).map((e) => (
          <li key={e.id} className={e.confirmed ? "stop confirmed" : "stop"}>
            <span className="dot" />
            <div className="stop-card">
              <p className="year">{e.year ?? e.date_text ?? "Время неизвестно"}</p>
              <h3>{e.title}</h3>
              {e.summary && <p>{e.summary}</p>}
              {e.place && <p className="muted">Место: {e.place}</p>}
              {e.people?.length > 0 && <p className="muted">Люди: {e.people.join(", ")}</p>}
              <div className="row small-row">
                <button className="chip" onClick={() => confirm(e)}>{e.confirmed ? "✓ Подтверждено" : "Подтвердить"}</button>
                <button className="chip" onClick={() => edit(e)}>Изменить</button>
                <button className="chip" onClick={() => remove(e)}>Убрать</button>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </main>
  );
}
