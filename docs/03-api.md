# 03. API

Базовый путь `/api`. Авторизация: заголовок `Authorization: Bearer <token>` (токен выдают `/auth/register` и `/auth/login`).
Ошибки: JSON `{"error": "код"}`.

## Служебное
| Метод и путь | Назначение |
|---|---|
| `GET /health` | статус, активные провайдеры LLM и STT (без авторизации) |
| `POST /api/auth/register` `{email, password}` | регистрация (пароль от 8 символов), 201 + `token` |
| `POST /api/auth/login` `{email, password}` | вход, `token` |
| `GET /api/bootstrap` | настройки, сценарий знакомства, вопросы мастера настроек, список модулей |
| `PUT /api/settings` `{settings, onboarded?}` | сохранить настройки (только разрешённые ключи) |

## Разговор
| Метод и путь | Назначение |
|---|---|
| `POST /api/session/start` | начать сессию, возвращает `session_id` и `next` |
| `GET /api/next` | следующий шаг |
| `POST /api/turn` | ответ человека: `multipart` (`audio`, `session_id`, `question_id`, `continue`) или JSON (`text`, ...). Ответ: `transcript`, `reply`, `next`, `auto_advance`, `recording_id`, `warnings`. При кризисной фразе `crisis: true` и `next: null` |
| `POST /api/skip` `{question_id}` | пропуск вопроса (после двух подряд вернёт `offer_break`) |
| `POST /api/gate` `{module_id, open}` | ответ на «ворота» чувствительной темы |
| `POST /api/module` `{module_id}` | выбор темы (режимы `by_theme`, `free`) |
| `POST /api/session/end` `{session_id}` | завершить сессию, вернёт `recap` |

Формат `next`:
- `{"type":"question","question":{id,module,module_title,text,sensitive,p},"bridge"?}`
- `{"type":"gate","module":{id,title},"text"}`
- `{"type":"choose_module","modules":[{id,title,gated}]}`
- `{"type":"offer_break","text"}`
- `{"type":"done"}`

## Записи
| `GET /api/recordings` | транскрипты (без кризисных) |
| `PATCH /api/recordings/<id>` `{transcript}` | исправить транскрипт (сбрасывает признак обработки событий) |

## Результаты
| Метод и путь | Назначение |
|---|---|
| `GET /api/timeline` | события «дороги жизни» |
| `POST /api/timeline/refresh` | извлечь события из новых транскриптов, вернёт `added` |
| `PATCH /api/timeline/<id>` `{title?, summary?, place?, date_text?, year?, confirmed?}` | правка и подтверждение |
| `DELETE /api/timeline/<id>` | убрать событие |
| `GET /api/chapters` | главы |
| `POST /api/chapters/generate` `{module_id?, force?}` | собрать главы по темам (подтверждённые не трогает без `force`) |
| `PATCH /api/chapters/<id>` `{title?, body?, status?}` | правка, статус `draft` или `confirmed` |
| `POST /api/chapters/<id>/comic` | раскадровка из главы |
| `GET /api/export/book.md`, `.html`, `.pdf` | экспорт книги (pdf: 501, если нет WeasyPrint) |

## Данные пользователя
| `GET /api/export/data.zip` | все данные и аудио |
| `DELETE /api/me` | удалить аккаунт и все данные |
