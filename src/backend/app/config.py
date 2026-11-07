"""Конфигурация из переменных окружения (см. .env.example в корне проекта)."""
import os
from pathlib import Path

DEFAULT_CRISIS_TEXT = (
    "Мне очень жаль, что вам сейчас так тяжело. Вы важны, и вы не одни. "
    "Пожалуйста, поговорите прямо сейчас с близким человеком. "
    "Если вам опасно или вы думаете о том, чтобы причинить себе вред, позвоните в экстренную службу: 112. "
    "В Германии также круглосуточно и бесплатно работает Telefonseelsorge: 0800 111 0 111 или 0800 111 0 222. "
    "Мы можем сделать паузу в записи. Я здесь, когда вы будете готовы вернуться."
)


def _bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self, env=None):
        e = os.environ if env is None else env
        self.secret_key = e.get("SECRET_KEY", "dev-secret-change-me")
        self.data_dir = Path(e.get("DATA_DIR", "./data")).resolve()
        self.db_path = self.data_dir / "app.db"
        self.audio_dir = self.data_dir / "audio"
        self.max_audio_mb = int(e.get("MAX_AUDIO_MB", "50"))
        self.registration_open = _bool(e.get("REGISTRATION_OPEN"), True)
        self.token_ttl_hours = int(e.get("TOKEN_TTL_HOURS", "720"))
        self.store_audio = _bool(e.get("STORE_AUDIO"), True)

        # LLM
        self.anthropic_api_key = e.get("ANTHROPIC_API_KEY", "")
        self.anthropic_model = e.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        default_llm = "anthropic" if self.anthropic_api_key else "mock"
        self.llm_provider = e.get("LLM_PROVIDER", default_llm)

        # STT: mock | faster_whisper | openai_compatible
        self.stt_provider = e.get("STT_PROVIDER", "mock")
        self.stt_language = e.get("STT_LANGUAGE", "de")
        self.whisper_model = e.get("WHISPER_MODEL", "large-v3-turbo")
        self.whisper_device = e.get("WHISPER_DEVICE", "auto")
        self.whisper_compute_type = e.get("WHISPER_COMPUTE_TYPE", "default")
        self.stt_api_key = e.get("STT_API_KEY", "")
        self.stt_base_url = e.get("STT_BASE_URL", "https://api.openai.com/v1")
        self.stt_api_model = e.get("STT_API_MODEL", "whisper-1")

        self.crisis_text = e.get("CRISIS_TEXT", DEFAULT_CRISIS_TEXT)
