SHELL := /bin/bash

AGENT ?= summarizer

.PHONY: bootstrap venv install run test docker-up docker-down github-oauth-check

bootstrap:
	./scripts/bootstrap.sh

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

# Requires gateway on 4280 (see `make run`). Optional: GITHUB_OAUTH_RETURN_TO=http://127.0.0.1:3000
github-oauth-check:
	bash scripts/check_github_oauth_local.sh
