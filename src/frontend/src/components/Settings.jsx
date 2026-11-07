import React, { useState } from "react";
import { api, setToken } from "../api.js";

export default function Settings({ settings, onRedo, onChange, onLogout }) {
  const [msg, setMsg] = useState("");

  async function toggle(key) {
    const value = !settings[key];
    const r = await api.put("/settings", { settings: { [key]: value } });
    onChange(r.settings);
  }

  async function wipe() {
    if (!window.confirm("Удалить ВСЕ ваши записи, главы и аккаунт? Это нельзя отменить.")) return;
    await api.del("/me");
    setToken("");
    onLogout();
  }

  return (
    <main className="card wide">
      <h2>Настройки</h2>
      <div className="stack">
        <button className="big" onClick={onRedo}>Изменить правила разговора</button>
        <button className="big" onClick={() => toggle("auto_continue")}>
          {settings.auto_continue ? "✓ " : ""}Сразу включать запись после вопроса
        </button>
        <button className="big" onClick={() => api.download("/export/data.zip", "meine-daten.zip").catch(() => setMsg("Не получилось скачать."))}>
          Скачать все мои данные
        </button>
        <button className="big danger" onClick={wipe}>Удалить все мои данные</button>
        <button className="link" onClick={() => { setToken(""); onLogout(); }}>Выйти</button>
      </div>
      {msg && <p className="error">{msg}</p>}
      <p className="muted">Помощник в этом приложении искусственный интеллект, а не человек. Он не заменяет врача или психолога.</p>
    </main>
  );
}
