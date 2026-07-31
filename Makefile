.PHONY: install fmt lint test cov precommit smoke weather-ab budget-scenarios geo-clusters route-benchmark multi-day-benchmark evaluate

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
