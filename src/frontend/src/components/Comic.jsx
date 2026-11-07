import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

// Комикс (этап 1): раскадровка с подписями. Генерация картинок это следующий этап (docs/06-roadmap.md).
export default function Comic() {
  const [chapters, setChapters] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => api.get("/chapters").then((r) => setChapters(r.chapters)), []);
  useEffect(() => { load(); }, [load]);

  async function make(ch) {
    setBusy(ch.id);
    setError("");
    try {
      await api.post(`/chapters/${ch.id}/comic`);
      await load();
    } catch (e) {
      setError("Не получилось сделать раскадровку.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="card wide">
      <h2>Комикс</h2>
      <p className="muted">Пока это раскадровка: сцены и подписи по вашим главам. Рисунки появятся в следующей версии.</p>
      {chapters && chapters.length === 0 && <p className="lead">Сначала соберите главы во вкладке «Книга».</p>}
      {error && <p className="error">{error}</p>}
      {(chapters || []).map((ch) => (
        <section key={ch.id} className="chapter">
          <h3>{ch.title}</h3>
          <button className="chip" disabled={busy === ch.id} onClick={() => make(ch)}>
            {busy === ch.id ? "Рисую раскадровку…" : ch.comic ? "Сделать заново" : "Сделать раскадровку"}
          </button>
          <div className="panels">
            {(ch.comic || []).map((s, i) => (
              <figure key={i} className="panel">
                <div className="panel-art">{s.visual}</div>
                <figcaption><strong>{s.title}</strong><br />{s.caption}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
