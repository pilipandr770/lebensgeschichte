import React, { useCallback, useEffect, useState } from "react";
import { api, hasToken } from "./api.js";
import Auth from "./components/Auth.jsx";
import Book from "./components/Book.jsx";
import Comic from "./components/Comic.jsx";
import Intro from "./components/Intro.jsx";
import Settings from "./components/Settings.jsx";
import Talk from "./components/Talk.jsx";
import Timeline from "./components/Timeline.jsx";
import Wizard from "./components/Wizard.jsx";

const TABS = [
  ["talk", "Рассказать"],
  ["road", "Дорога жизни"],
  ["book", "Книга"],
  ["comic", "Комикс"],
  ["settings", "Настройки"],
];

export default function App() {
  const [authed, setAuthed] = useState(hasToken());
  const [boot, setBoot] = useState(null);
  const [settings, setSettings] = useState({});
  const [stage, setStage] = useState("loading"); // loading | intro | wizard | app
  const [tab, setTab] = useState("talk");

  const load = useCallback(async () => {
    try {
      const b = await api.get("/bootstrap");
      setBoot(b);
      setSettings(b.settings);
      setStage(b.onboarded ? "app" : "intro");
    } catch (e) {
      setAuthed(false);
    }
  }, []);

  useEffect(() => {
    const out = () => setAuthed(false);
    window.addEventListener("lg-logout", out);
    return () => window.removeEventListener("lg-logout", out);
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  if (!authed) return <Auth onAuthed={() => setAuthed(true)} />;
  if (stage === "loading" || !boot) return <main className="card"><p className="lead">Загрузка…</p></main>;
  if (stage === "intro") return <Intro steps={boot.intro_steps} onDone={() => setStage("wizard")} />;
  if (stage === "wizard")
    return <Wizard questions={boot.settings_questions} initial={settings} onDone={(s) => { setSettings(s); setStage("app"); setTab("talk"); }} />;

  return (
    <>
      <nav className="tabs" aria-label="Разделы">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "tab active" : "tab"} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>
      {boot.llm_provider === "mock" && <p className="banner">Тестовый режим: ИИ и распознавание речи это заглушки. Подключите ключи в .env.</p>}
      {tab === "talk" && <Talk key="talk" settings={settings} />}
      {tab === "road" && <Timeline />}
      {tab === "book" && <Book />}
      {tab === "comic" && <Comic />}
      {tab === "settings" && (
        <Settings settings={settings} onChange={setSettings} onRedo={() => setStage("wizard")} onLogout={() => setAuthed(false)} />
      )}
    </>
  );
}
