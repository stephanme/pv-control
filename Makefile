# Makefile for easy development workflows.
# Note GitHub Actions call uv directly, not this Makefile.

.DEFAULT_GOAL := default

.PHONY: default install lint test upgrade build clean

default: install lint test 

install:
	uv sync --all-extras
	(cd ui && npm install)

lint:
	uv run ruff check
	uv run ruff format --check
	uv run ty check
	(cd ui && ng lint)

test:
	uv run python -m unittest discover -v -s tests
	# (cd ui && ng test --no-watch --no-progress)

upgrade:
	uv sync --upgrade --all-extras --dev

build:
	(cd ui && ng build --configuration production)
	uv build

clean:
	-rm -rf dist/
	-rm -rf *.egg-info/
	-rm -rf .pytest_cache/
	-rm -rf .ruff_cache/
	-rm -rf .venv/
	-find . -type d -name "__pycache__" -exec rm -rf {} +
