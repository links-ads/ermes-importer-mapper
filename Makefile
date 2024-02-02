.ONESHELL:
PY_ENV=.venv
PY_BIN=$(shell python -c "print('$(PY_ENV)/bin') if __import__('pathlib').Path('$(PY_ENV)/bin/pip').exists() else print('')")

.DEFAULT_GOAL := help
DOCKER_COMPOSE := docker compose -f docker-compose.yml -f docker-compose.$(TARGET).yml

.PHONY: help
help:				## This help screen
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##//'

.PHONY: check-venv
check-venv:			## Check if the virtualenv exists.
	@if [ "$(PY_BIN)" = "" ]; then echo "No virtualenv detected, create one using 'make virtualenv'"; exit 1; fi

.PHONY: install
install: check-venv		## Install the project in dev mode.
	@$(PY_BIN)/pip install -e .[dev,docs,test]

.PHONY: fmt
fmt: check-venv			## Format code using black & isort.
	$(PY_BIN)/isort -v --src src/ --virtual-env $(PY_ENV)
	$(PY_BIN)/black src/

.PHONY: lint
lint: check-venv		## Run ruff, black, mypy (optional).
	@$(PY_BIN)/ruff check src/
	@$(PY_BIN)/black --check src/
	@if [ -x "$(PY_BIN)/mypy" ]; then $(PY_BIN)/mypy src/; else echo "mypy not installed, skipping"; fi

.PHONY: clean
clean:				## Clean unused files (VENV=true to also remove the virtualenv).
	@find ./ -name '*.pyc' -exec rm -f {} \;
	@find ./ -name '__pycache__' -exec rm -rf {} \;
	@find ./ -name 'Thumbs.db' -exec rm -f {} \;
	@find ./ -name '*~' -exec rm -f {} \;
	@rm -rf .cache
	@rm -rf .pytest_cache
	@rm -rf .mypy_cache
	@rm -rf .ruff_cache
	@rm -rf build
	@rm -rf dist
	@rm -rf *.egg-info
	@rm -rf htmlcov
	@rm -rf .tox/
	@rm -rf docs/_build
	@if [ "$(VENV)" != "" ]; then echo "Removing virtualenv..."; rm -rf $(PY_ENV); fi

.PHONY: check-target
check-target:				## Check if TARGET variable is set.
	@if [ -z "$(TARGET)" ]; then echo "TARGET is not set, launch the command setting TARGET=dev|prod"; exit 1; fi
	@if [ "$(TARGET)" != "dev" ] && [ "$(TARGET)" != "prod" ]; then echo "TARGET must be either dev or prod"; exit 1; fi
	@echo "Symlinking .env file to $${TARGET}.env"
	@ln -sf ./envs/$${TARGET}.env .env

.PHONY: config
config:	check-target		## Build the compose project.
	@echo "Configuring compose with target: $${TARGET}"
	@$(DOCKER_COMPOSE) config $${ARGS}

.PHONY: build
build:	check-target		## Build the compose project.
	@echo "Building images with target: $${TARGET}"
	@$(DOCKER_COMPOSE) build $${ARGS}

.PHONY: up
up: check-target			## Start the project containers.
	@echo "Starting containers with target: $${TARGET}"
	@$(DOCKER_COMPOSE) up $${ARGS}

stop: check-target			## Stop the project containers.
	@echo "Stopping containers with target: $${TARGET}"
	@$(DOCKER_COMPOSE) stop $${ARGS}

.PHONY: down
down: check-target			## Stop the project eliminating containers, use ARGS="-v" to remove volumes.
	@echo "Stopping containers with target: $${TARGET}"
	@$(DOCKER_COMPOSE) down $${ARGS}
