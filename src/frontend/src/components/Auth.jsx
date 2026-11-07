import React, { useState } from "react";
import { api, setToken } from "../api.js";

export default function Auth({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const messages = {
    invalid_credentials: "Неверная почта или пароль.",
    email_taken: "Эта почта уже зарегистрирована.",
    invalid_email: "Проверьте адрес почты.",
    password_too_short: "Пароль должен быть не короче 8 символов.",
    registration_closed: "Регистрация сейчас закрыта.",
  };

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.post(`/auth/${mode}`, { email, password });
      setToken(r.token);
      onAuthed();
    } catch (err) {
      setError(messages[err.message] || "Не получилось. Попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="card narrow">
      <h1>Lebensgeschichte</h1>
      <p className="lead">Ваша история в ваших словах. Я послушаю, а потом из рассказов получится книга.</p>
      <form onSubmit={submit}>
        <label>
          Электронная почта
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="big primary" disabled={busy}>{mode === "login" ? "Войти" : "Создать аккаунт"}</button>
      </form>
      <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Первый раз здесь? Создать аккаунт" : "Уже есть аккаунт? Войти"}
      </button>
    </main>
  );
}
