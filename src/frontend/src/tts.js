// Озвучка через встроенный синтезатор браузера (бесплатно, работает без сервера).
// Для более естественного голоса позже можно заменить на серверный TTS (см. docs/06-roadmap.md).
export function ttsSupported() {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function cancelSpeech() {
  if (ttsSupported()) window.speechSynthesis.cancel();
}

export function speak(text, { lang = "de-DE", slow = false } = {}) {
  return new Promise((resolve) => {
    if (!ttsSupported() || !text) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = slow ? 0.85 : 1;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

// Грубое определение языка по алфавиту, чтобы выбрать голос для вопросов на русском или немецком.
export function guessLang(text) {
  return /[А-Яа-яЁё]/.test(text || "") ? "ru-RU" : "de-DE";
}
