.DEFAULT_GOAL := help
.ONESHELL:
SHELL := /bin/sh
.SHELLFLAGS := -eu -c

ENDPOINT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
DOCKER ?= docker
PYTHON ?= python3
VERSION ?= 0.0.1
DATABASE_VERSION ?= 0.0.1
DUCKDB_JDBC_VERSION ?= 1.5.6.0
REPOSITORY ?= ghcr.io/provider-project/sparql-faostat-ontop
IMAGE ?= $(REPOSITORY):$(VERSION)
DATA_REPOSITORY_URL ?= https://maven.inf-ai.duckdns.org/releases
PORT ?= 8081
GHCR_USER ?=

COMPOSE = FAOSTAT_IMAGE="$(IMAGE)" ENDPOINT_VERSION="$(VERSION)" \
	FAOSTAT_VERSION="$(DATABASE_VERSION)" DUCKDB_JDBC_VERSION="$(DUCKDB_JDBC_VERSION)" \
	FAOSTAT_REPOSITORY_URL="$(DATA_REPOSITORY_URL)" ONTOP_PORT="$(PORT)" \
	$(DOCKER) compose --project-directory "$(ENDPOINT_DIR)" -f "$(ENDPOINT_DIR)/docker-compose.yaml"

.PHONY: help show-config build check test login publish up down logs ps

help: ## Show available targets (the default)
	@awk 'BEGIN { FS = ":.*## " } /^[[:alnum:]_.-]+:.*## / { printf "make %-24s # %s\n", $$1, $$2 }' "$(ENDPOINT_DIR)/Makefile"
	printf '\nOverrides: VERSION DATABASE_VERSION DUCKDB_JDBC_VERSION REPOSITORY IMAGE PORT GHCR_USER\n'

show-config: ## Show the selected image, artifact versions and host port
	@printf '%-22s %s\n' \
		IMAGE "$(IMAGE)" VERSION "$(VERSION)" DATABASE_VERSION "$(DATABASE_VERSION)" \
		DUCKDB_JDBC_VERSION "$(DUCKDB_JDBC_VERSION)" DATA_REPOSITORY_URL "$(DATA_REPOSITORY_URL)" PORT "$(PORT)"

build: ## Build the endpoint image from a published database release
	cd "$(ENDPOINT_DIR)"
	$(DOCKER) build --tag "$(IMAGE)" \
		--build-arg ENDPOINT_VERSION="$(VERSION)" \
		--build-arg FAOSTAT_VERSION="$(DATABASE_VERSION)" \
		--build-arg DUCKDB_JDBC_VERSION="$(DUCKDB_JDBC_VERSION)" \
		--build-arg FAOSTAT_REPOSITORY_URL="$(DATA_REPOSITORY_URL)" .

check: ## Check Makefile orchestration without Docker or network access
	cd "$(ENDPOINT_DIR)"
	$(PYTHON) -m unittest discover -s tests -p test_makefile.py -v

test: check build ## Build and run isolated SPARQL/image integration checks
	cd "$(ENDPOINT_DIR)"
	FAOSTAT_ENDPOINT_IMAGE="$(IMAGE)" $(PYTHON) -m unittest discover -s tests -p test_endpoint_image.py -v

login: ## Log in to GHCR (set GHCR_USER; enter a classic PAT at the password prompt)
	@test -n "$(GHCR_USER)" || { printf '%s\n' 'Set GHCR_USER to your personal GitHub username.' >&2; exit 1; }
	$(DOCKER) login ghcr.io --username "$(GHCR_USER)"

publish: build ## Build and push the selected image (authenticate separately)
	$(DOCKER) push "$(IMAGE)"

up: build ## Build and start the local Compose service on PORT
	$(COMPOSE) up --detach --no-build

down: ## Stop and remove this Compose service
	$(COMPOSE) down

logs: ## Follow this Compose service's logs
	$(COMPOSE) logs --follow ontop

ps: ## Show this Compose service's status
	$(COMPOSE) ps
