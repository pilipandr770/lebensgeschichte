# Backend (Flask)

- Точка входа: `wsgi.py`, фабрика `app/__init__.py:create_app`.
- Модули: `api.py` (маршруты), `auth.py`, `db.py` (SQLite), `questions.py` (движок вопросов), `llm.py` + `prompts.py` (Claude/mock), `stt.py` (Whisper/API/mock), `exports.py` (книга, архив), `safety.py` (кризис).
- Провайдеры выбираются переменными окружения (`LLM_PROVIDER`, `STT_PROVIDER`). Без ключей всё работает в mock-режиме, на этом строятся тесты.
- Запуск тестов: `python3 -m unittest discover -s tests -t . -v` (из этой папки).
- Новые настройки добавлять в `SETTING_KEYS` (`api.py`), в `onboarding.json` и в `docs/`.
- Новые теги: добавить в `TAG_KEYS` (`questions.py`), решить, чувствительный ли (`SENSITIVE_TAGS`), добавить `extract` у вопроса.
- Для продакшена с несколькими воркерами заменить SQLite на Postgres (см. `docs/05-deployment.md`).
