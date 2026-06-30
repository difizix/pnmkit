.PHONY: all test lint format

all: lint test

test:
	python3 -m pytest

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .
