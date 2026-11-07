import json

from .config import Config
from .llm import make_llm
from .questions import DATA_DIR, QuestionBank
from .stt import make_stt


class Services:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.bank = QuestionBank.from_file()
        self.onboarding = json.loads((DATA_DIR / "onboarding.json").read_text(encoding="utf-8"))
        self.llm = make_llm(cfg)
        self.stt = make_stt(cfg)
