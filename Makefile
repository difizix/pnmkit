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

clean:
	rm -rf __pycache__ */__pycache__ */*/__pycache__
