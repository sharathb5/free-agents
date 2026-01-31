SHELL := /bin/bash

AGENT ?= summarizer

.PHONY: venv install run test docker-up docker-down

venv:
	python3 -m venv .venv

install: venv
	source .venv/bin/activate && python -m pip install -U pip && python -m pip install -r requirements.txt

run: install
	source .venv/bin/activate && AGENT_PRESET="$(AGENT)" uvicorn app.main:app --host 0.0.0.0 --port 4280

test: install
	source .venv/bin/activate && python -m pytest -q

docker-up:
	AGENT_PRESET="$(AGENT)" docker compose up --build

docker-down:
	docker compose down

