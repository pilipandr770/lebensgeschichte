from flask import Flask, jsonify

from . import db as dbmod
from .api import bp as api_bp
from .auth import bp as auth_bp
from .config import Config
from .services import Services


def create_app(config=None):
    cfg = config or Config()
    app = Flask(__name__)
    app.config["CFG"] = cfg
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_audio_mb * 1024 * 1024
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.audio_dir.mkdir(parents=True, exist_ok=True)
    dbmod.init_db(cfg.db_path)
    app.extensions["services"] = Services(cfg)
    app.teardown_appcontext(dbmod.close_db)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.get("/health")
    def health():
        return jsonify(status="ok", llm=cfg.llm_provider, stt=cfg.stt_provider)

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify(error="file_too_large"), 413

    return app
