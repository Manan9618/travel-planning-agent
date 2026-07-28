.PHONY: install fmt lint test cov precommit smoke

install:
	poetry install
	poetry run pre-commit install

fmt:
	poetry run black src tests
	poetry run ruff check --fix src tests

lint:
	poetry run ruff check src tests
	poetry run black --check src tests

test:
	poetry run pytest

cov:
	poetry run pytest --cov=travel_agent --cov-report=term-missing

precommit:
	poetry run pre-commit run --all-files

smoke:
	poetry run python scripts/smoke_test_apis.py
