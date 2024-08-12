.PHONY: update-deps
update-deps:
	pip install --upgrade uv
	uv pip compile --upgrade --build-isolation --generate-hashes --output-file requirements/main.txt requirements/main.in
	uv pip compile --upgrade --build-isolation --generate-hashes --output-file requirements/dev.txt requirements/dev.in

.PHONY: init
init:
	pip install --upgrade uv
	uv pip install --editable .
	uv pip install --upgrade -r requirements/main.txt -r requirements/dev.txt
	rm -rf .tox
	uv pip install --upgrade tox
	pre-commit install

.PHONY: update
update: update-deps init
