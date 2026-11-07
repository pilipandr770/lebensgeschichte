#!/usr/bin/env python3
"""Проверка банка вопросов: уникальные id, существующие модули, корректные условия if, допустимые теги.
Запуск из src/backend: python3 ../../tools/validate_questions.py [путь/к/questions.json]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from app.questions import QuestionBank  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else None
bank = QuestionBank.from_file(path)
errors = bank.validate()
mods = {}
for q in bank.questions:
    mods[q["m"]] = mods.get(q["m"], 0) + 1
print(f"Вопросов: {len(bank.questions)}, модулей: {len(bank.modules)}")
for m in bank.modules:
    print(f"  {m['id']:<10} {mods.get(m['id'], 0):>3}  {m['title']}")
if errors:
    print("\nОШИБКИ:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("\nOK: ошибок нет")
