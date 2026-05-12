.PHONY: help install test test-fast lint fmt typecheck cov build clean rules-doc rules-doc-check examples

PY := .venv/bin/python
UV := uv

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-14s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Sync deps + dev extras via uv.
	$(UV) sync --extra dev

test:  ## Run the full test suite with coverage (matches CI).
	$(PY) -m pytest --no-header

test-fast:  ## Run tests without coverage (faster local loop).
	$(PY) -m pytest --no-header -q --no-cov

lint:  ## ruff check (no auto-fix).
	$(PY) -m ruff check humanize_en tests

fmt:  ## ruff check --fix + format.
	$(PY) -m ruff check --fix humanize_en tests
	$(PY) -m ruff format humanize_en tests

typecheck:  ## mypy on the package.
	$(PY) -m mypy humanize_en

cov:  ## Detailed coverage report by module.
	$(PY) -m pytest --no-header --cov-report=term-missing

build:  ## Build sdist + wheel into dist/.
	$(UV) build

clean:  ## Remove build artifacts and caches.
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

rules-doc:  ## Regenerate docs/rules.md from rules.json.
	$(PY) scripts/gen_rules_doc.py

rules-doc-check:  ## Fail if docs/rules.md is out of sync (CI gate).
	$(PY) scripts/gen_rules_doc.py --check

examples:  ## Run the no-LLM examples (01, 04) — fast smoke check.
	$(PY) examples/01_detect_only.py
	@echo
	$(PY) examples/04_inject_rules_into_prompt.py
