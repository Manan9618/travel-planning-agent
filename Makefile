.PHONY: install fmt lint test cov precommit smoke weather-ab budget-scenarios geo-clusters route-benchmark multi-day-benchmark evaluate map-test pdf-test serve frontend-install frontend-dev frontend-build frontend-test frontend-lint

install:
	poetry install
	poetry run pre-commit install
	poetry run playwright install chromium

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

weather-ab:
	poetry run python scripts/weather_ab_test.py

budget-scenarios:
	poetry run python scripts/budget_scenarios_test.py

geo-clusters:
	poetry run python scripts/geo_clustering_test.py

route-benchmark:
	poetry run python scripts/route_optimization_benchmark.py

multi-day-benchmark:
	poetry run python scripts/multi_day_optimizer_benchmark.py

evaluate:
	poetry run python scripts/agent_evaluation.py

map-test:
	poetry run python scripts/map_generation_test.py

pdf-test:
	poetry run python scripts/pdf_generation_test.py

serve:
	poetry run uvicorn travel_agent.api.app:create_app --factory --reload --app-dir src

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm test

frontend-lint:
	cd frontend && npm run lint
