"""Распознавание речи: mock | faster_whisper (локально, ЕС-сервер) | openai_compatible (облачный API)."""
import logging
import uuid

log = logging.getLogger(__name__)


class MockSTT:
    def transcribe(self, path, language, prompt=None):
        return "[mock-транскрипт: STT_PROVIDER=mock, подключите настоящий провайдер в .env]"


class FasterWhisperSTT:
    _model = None

    def __init__(self, cfg):
        self.cfg = cfg

    def _load(self):
        if FasterWhisperSTT._model is None:
            from faster_whisper import WhisperModel  # ленивый импорт: тяжёлая зависимость
            FasterWhisperSTT._model = WhisperModel(self.cfg.whisper_model, device=self.cfg.whisper_device,
                                                   compute_type=self.cfg.whisper_compute_type)
        return FasterWhisperSTT._model

    def transcribe(self, path, language, prompt=None):
        model = self._load()
        segments, _info = model.transcribe(str(path), language=language or None, vad_filter=True,
                                           initial_prompt=prompt or None, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()


class OpenAICompatibleSTT:
    def __init__(self, cfg):
        self.cfg = cfg

    def transcribe(self, path, language, prompt=None):
        import requests
        url = self.cfg.stt_base_url.rstrip("/") + "/audio/transcriptions"
        with open(path, "rb") as fh:
            files = {"file": (path.name, fh)}
            data = {"model": self.cfg.stt_api_model}
            if language:
                data["language"] = language
            if prompt:
                data["prompt"] = prompt
            r = requests.post(url, headers={"Authorization": f"Bearer {self.cfg.stt_api_key}"},
                              files=files, data=data, timeout=300)
        r.raise_for_status()
        return (r.json().get("text") or "").strip()


def make_stt(cfg):
    if cfg.stt_provider == "faster_whisper":
        return FasterWhisperSTT(cfg)
    if cfg.stt_provider == "openai_compatible":
        return OpenAICompatibleSTT(cfg)
    return MockSTT()


def audio_extension(mimetype):
    mt = (mimetype or "").lower()
    if "webm" in mt:
        return ".webm"
    if "mp4" in mt or "m4a" in mt or "aac" in mt:
        return ".m4a"
    if "ogg" in mt:
        return ".ogg"
    if "wav" in mt:
        return ".wav"
    if "mpeg" in mt or "mp3" in mt:
        return ".mp3"
    return ".bin"


def new_audio_name(mimetype):
    return uuid.uuid4().hex + audio_extension(mimetype)
