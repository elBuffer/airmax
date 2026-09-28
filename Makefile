PY := PYTHONWARNINGS=ignore::DeprecationWarning uv run python

.PHONY: install install-hooks lint typecheck pre-commit replay replay-data capture-ircel replay-ircel serve test docker-test docker-replay package deploy

install:
	uv sync

install-hooks:
	git config core.hooksPath .githooks

lint:
	uv run ruff check services tests tools
	uv run ruff format --check services tests tools

typecheck:
	uv run mypy

pre-commit: lint typecheck
	AIRMAX_LOCAL_ROOT=.local/pre-commit $(PY) tools/replay.py
	$(PY) -m unittest discover -s tests

replay:
	$(PY) tools/replay.py

replay-data:
	AIRMAX_DATA=data/openaq-andre-raw.jsonl $(PY) tools/replay.py

capture-ircel:
	$(PY) tools/capture_ircel.py --start "$(START)" --end "$(END)"

replay-ircel:
	AIRMAX_DATA=$(or $(DATA),data/ircel.ndjson) $(PY) tools/replay_ircel.py

serve:
	AIRMAX_STORE=local $(PY) -m airmax_website.handler

test:
	$(PY) -m unittest discover -s tests

docker-test:
	docker compose run --rm --build test

docker-replay:
	docker compose run --rm --build replay

package:
	$(PY) tools/package_lambdas.py

TF := powershell.exe -NoProfile -ExecutionPolicy Bypass -File with-env.ps1 terraform -chdir=infra/terraform

# Saves a reviewed plan only; apply it yourself with: terraform apply $(STAGE).tfplan
deploy: package
	$(if $(filter dev qa prd,$(STAGE)),,$(error STAGE must be dev, qa or prd))
	$(TF) init
	$(TF) workspace select -or-create=true $(STAGE)
	$(TF) plan -out=$(STAGE).tfplan
