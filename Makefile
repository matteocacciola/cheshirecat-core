UID := $(shell id -u)
GID := $(shell id -g)
PWD = $(shell pwd)

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
	@docker exec cheshire_cat_core uv run python -m pytest --color=yes -vvv -W ignore --disable-warnings ${args}

install: ## Update the local virtual environment with the latest requirements.
	@# install the requirements
	@uv sync --link-mode=copy --frozen --locked --no-install-project
	@# look for requirements.txt in subdirectories of core_plugins and install them
	@find $(PWD)/cat/core_plugins -name requirements.txt -exec uv pip install --link-mode=copy -r {} \;
	@pip cache purge

update: ## Update and compile requirements for the local virtual environment.
	@# upgrade the requirements
	@uv sync --upgrade --link-mode=copy

check: ## Check requirements for the local virtual environment.
	@uv sync --check
