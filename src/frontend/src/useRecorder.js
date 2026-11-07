import { useCallback, useEffect, useRef, useState } from "react";

const VOICE_THRESHOLD = 0.015; // RMS; подбирается на реальных устройствах

function pickMime() {
  const cands = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  if (typeof MediaRecorder === "undefined") return "";
  return cands.find((c) => MediaRecorder.isTypeSupported(c)) || "";
}

/**
 * Запись голоса одной кнопкой. Остановка автоматическая: когда человек замолчал дольше pauseSeconds
 * (после того как хоть раз заговорил), либо по кнопке, либо по лимиту maxSeconds.
 */
export function useRecorder({ pauseSeconds = 4, maxSeconds = 600, onFinish }) {
  const [state, setState] = useState("idle"); // idle | recording
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");
  const refs = useRef({});
  const finishRef = useRef(onFinish);
  finishRef.current = onFinish;

  const cleanup = useCallback(() => {
    const r = refs.current;
    clearInterval(r.timer);
    r.stream?.getTracks().forEach((t) => t.stop());
    r.ctx?.close().catch(() => {});
    refs.current = {};
    setLevel(0);
    setState("idle");
  }, []);

  const stop = useCallback(() => {
    const r = refs.current;
    if (r.rec && r.rec.state !== "inactive") r.rec.stop();
    else cleanup();
  }, [cleanup]);

  const start = useCallback(async () => {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMime();
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      const chunks = [];
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Float32Array(analyser.fftSize);
      const state0 = { heard: false, lastVoice: Date.now(), startedAt: Date.now() };

      rec.ondataavailable = (e) => e.data && e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        const blob = new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" });
        const heard = state0.heard;
        cleanup();
        if (heard && blob.size > 0) finishRef.current?.(blob, blob.type);
        else finishRef.current?.(null, "");
      };
      rec.start(5000); // кусок каждые 5 секунд, чтобы данные не накапливались одним блоком

      const timer = setInterval(() => {
        analyser.getFloatTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
        const rms = Math.sqrt(sum / buf.length);
        setLevel(Math.min(1, rms * 12));
        const now = Date.now();
        if (rms > VOICE_THRESHOLD) {
          state0.heard = true;
          state0.lastVoice = now;
        }
        const silentFor = (now - state0.lastVoice) / 1000;
        if (state0.heard && silentFor >= pauseSeconds) stop();
        else if ((now - state0.startedAt) / 1000 >= maxSeconds) stop();
      }, 200);

      refs.current = { rec, stream, ctx, timer };
      setState("recording");
    } catch (e) {
      cleanup();
      setError("Не удалось включить микрофон. Разрешите доступ к микрофону в браузере.");
    }
  }, [pauseSeconds, maxSeconds, cleanup, stop]);

  useEffect(() => () => cleanup(), [cleanup]);

  return { state, level, error, start, stop };
}
