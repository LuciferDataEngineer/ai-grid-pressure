PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: install build test lint ci up trino-smoke

install:
	$(PIP) install -e ".[dev]"

build:
	$(PY) -m gridpressure

test:
	$(PY) -m pytest -q tests/unit

lint:
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests

ci: lint test build
	$(PY) -m pytest -q tests/integration

up:
	docker compose up -d

trino-smoke:
	$(PY) scripts/trino_smoke.py
