import React, { useState } from "react";
import { cancelSpeech, guessLang, speak } from "../tts.js";

// Этап A: знакомство. Приложение честно говорит, что оно ИИ, и объясняет правила.
export default function Intro({ steps, onDone }) {
  const [i, setI] = useState(0);
  const step = steps[i];

  function next() {
    cancelSpeech();
    if (i + 1 >= steps.length) onDone();
    else setI(i + 1);
  }

  return (
    <main className="card">
      <p className="muted">Знакомство · {i + 1} из {steps.length}</p>
      <p className="lead big-text">{step.say}</p>
      {step.check && <p className="check">{step.check}</p>}
      <div className="row">
        <button className="big primary" onClick={next}>
          {i + 1 >= steps.length ? "Настроить разговор" : step.check ? "Да, дальше" : "Дальше"}
        </button>
        <button className="big" onClick={() => speak(step.say, { lang: guessLang(step.say) })}>Прочитать вслух</button>
      </div>
    </main>
  );
}
