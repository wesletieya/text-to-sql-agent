MODEL ?= qwen2.5-coder:7b
RUNS ?= 3

.PHONY: data catalog ask test lint format eval report api ui app

data:
	uv run --env-file .env python -m scripts.download_olist
	uv run --env-file .env python -m scripts.generate_tpch
	uv run --env-file .env python -m scripts.build_lakehouse

catalog:
	uv run python -m scripts.build_catalog

ask:
	uv run --env-file .env python -m agent.pipeline "$(Q)" --model $(MODEL)

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

eval:
	uv run --env-file .env python -m eval.run --model $(MODEL) --runs $(RUNS)

report:
	uv run python -m eval.report

api:
	uv run uvicorn app.api:app --reload

ui:
	uv run streamlit run app/ui.py

# Phase 7: will start the API and the UI together.
app:
	@echo "make app arrives in Phase 7; meanwhile use 'make api' and 'make ui' in two terminals."
