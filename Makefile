UID := $(shell id -u)
GID := $(shell id -g)
PWD = $(shell pwd)

LOCAL_DIR = $(PWD)/venv/bin
PYTHON = $(LOCAL_DIR)/python
PYTHON3 = python3.10
PIP_SYNC = $(PYTHON) -m piptools sync --python-executable $(PYTHON)
PIP_COMPILE = $(PYTHON) -m piptools compile --strip-extras

args=
# if dockerfile is not defined
ifndef dockerfile
	dockerfile=compose.yml
endif

docker-compose-files=-f ${dockerfile}

help:  ## Show help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n"} /^[$$()% a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

build:  ## Build docker image(s) [args="<name_of_image>"].
	@docker compose $(docker-compose-files) build ${args}

build-no-cache:  ## Build docker image(s) without cache [args="<name_of_image>"].
	@docker compose $(docker-compose-files) --compatibility build ${args} --no-cache

up:  ## Start docker container(s) [args="<name_of_service>"].
	@docker compose ${docker-compose-files} up ${args} -d

down:  ## Stop docker container(s) [args="<name_of_service>"].
	@docker compose ${docker-compose-files} down ${args}

stop:  ## Stop docker containers [args="<name_of_service>"].
	@docker compose ${docker-compose-files} stop ${args}

restart:  ## Restart service(s) [args="<name_of_service>"].
	@docker compose ${docker-compose-files} restart ${args}

test:  ## Run tests.
	@docker exec cheshire_cat_core python -m pytest --color=yes -vvv -W ignore ${args}

install: ## Update the local virtual environment with the latest requirements.
	@$(PYTHON) -m pip install --upgrade pip-tools pip wheel
	@$(PIP_SYNC) requirements.txt
	@$(PYTHON) -m pip install -r requirements.txt
	# look for requirements.txt in subdirectories of core_plugins and install them
	@find $(PWD)/cheshirecat/core_plugins -name requirements.txt -exec $(PYTHON) -m pip install -r {} \;

compile: ## Compile requirements for the local virtual environment.
	@$(PIP_COMPILE) --no-upgrade --output-file requirements.txt pyproject.toml

update: ## Update and compile requirements for the local virtual environment.
	@$(PIP_COMPILE) --upgrade --output-file requirements.txt pyproject.toml
