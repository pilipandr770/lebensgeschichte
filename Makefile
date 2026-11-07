.PHONY: setup test dev-backend dev-frontend up down validate seed

setup:
	cd src/backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt
	cd src/frontend && npm install
	@test -f .env || cp .env.example .env

test:
	cd src/backend && python3 -m unittest discover -s tests -t . -v

validate:
	cd src/backend && python3 ../../tools/validate_questions.py

dev-backend:
	cd src/backend && DATA_DIR=../../data python3 -m flask --app wsgi run --port 8000 --debug

dev-frontend:
	cd src/frontend && npm run dev

seed:
	cd src/backend && DATA_DIR=../../data python3 ../../tools/seed_demo.py

up:
	docker compose up --build -d

down:
	docker compose down
