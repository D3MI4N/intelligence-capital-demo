.PHONY: check fmt lint type test

check: fmt lint type test

fmt:
	uv run ruff format --check .

lint:
	uv run ruff check .

type:
	uv run mypy .

test:
	uv run pytest