MODEL ?= claude-sonnet-5-5

.PHONY: data test lint format eval api ui app

data:
	uv run python -m scripts.download_olist
	uv run python -m scripts.generate_tpch
	uv run python -m scripts.build_lakehouse

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

eval:
	uv run python -m eval.run --model $(MODEL) --runs 3

api:
	uv run uvicorn app.api:app --reload

ui:
	uv run streamlit run app/ui.py

# Phase 7: will start the API and the UI together.
app:
	@echo "make app arrives in Phase 7; meanwhile use 'make api' and 'make ui' in two terminals."
