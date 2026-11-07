import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

// Книга: главы собираются из рассказов, человек (или семья) читает, правит и подтверждает.
export default function Book() {
  const [chapters, setChapters] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [drafts, setDrafts] = useState({});

  const load = useCallback(() => api.get("/chapters").then((r) => { setChapters(r.chapters); setDrafts({}); }), []);
  useEffect(() => { load(); }, [load]);

  async function generate() {
    setBusy(true);
    setMsg("");
    try {
      const r = await api.post("/chapters/generate", {});
      setMsg(r.generated.length ? "Главы готовы. Прочитайте и поправьте, если нужно." : "Новых глав пока нет.");
      await load();
    } catch (e) {
      setMsg("Не получилось собрать главы.");
    } finally {
      setBusy(false);
    }
  }

  async function save(ch, status) {
    const body = drafts[ch.id] ?? ch.body;
    await api.patch(`/chapters/${ch.id}`, { body, ...(status ? { status } : {}) });
    load();
  }

  async function exportBook(fmt) {
    try {
      await api.download(`/export/book.${fmt}`, `lebensgeschichte.${fmt}`);
    } catch (e) {
      setMsg(fmt === "pdf" ? "PDF пока недоступен на этом сервере. Скачайте HTML и распечатайте из браузера." : "Не получилось скачать.");
    }
  }

  return (
    <main className="card wide">
      <h2>Книга</h2>
      <div className="row">
        <button className="big primary" disabled={busy} onClick={generate}>{busy ? "Пишу главы…" : "Собрать главы из рассказов"}</button>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {chapters && chapters.length === 0 && <p className="lead">Глав пока нет. Сначала расскажите что-нибудь.</p>}
      {(chapters || []).map((ch) => (
        <section key={ch.id} className="chapter">
          <h3>{ch.title} <span className={"badge " + ch.status}>{ch.status === "confirmed" ? "подтверждена" : "черновик"}</span></h3>
          <textarea rows={12} value={drafts[ch.id] ?? ch.body} onChange={(e) => setDrafts({ ...drafts, [ch.id]: e.target.value })} />
          <p className="muted">Места со знаком [?] нужно уточнить.</p>
          <div className="row small-row">
            <button className="chip" onClick={() => save(ch)}>Сохранить правки</button>
            <button className="chip" onClick={() => save(ch, ch.status === "confirmed" ? "draft" : "confirmed")}>
              {ch.status === "confirmed" ? "Вернуть в черновик" : "Всё верно, подтверждаю"}
            </button>
          </div>
        </section>
      ))}
      {chapters && chapters.length > 0 && (
        <div className="row">
          <button className="big" onClick={() => exportBook("pdf")}>Скачать PDF</button>
          <button className="big" onClick={() => exportBook("html")}>Скачать HTML</button>
          <button className="big" onClick={() => exportBook("md")}>Скачать текст</button>
        </div>
      )}
    </main>
  );
}
