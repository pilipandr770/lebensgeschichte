Переведи банк вопросов `src/backend/app/data/questions.json` и сценарий `onboarding.json` на немецкий.
Требования: обращение на «Sie» по умолчанию, тёплый разговорный тон без канцелярита, короткие фразы, без просторечий и диалектов; сохрани id, условия `if`, `extract`, `sensitive`, структуру. Плейсхолдеры {partner} подставляются именем, поэтому формулировки не должны зависеть от падежа.
Создай файлы `questions.de.json` и `onboarding.de.json`, затем добавь выбор языка в `app/questions.py` и `app/services.py` (переменная `APP_LANG`), и обнови тесты. Запусти `make validate` и `make test`.
