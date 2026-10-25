.DEFAULT_GOAL := help
.ONESHELL:
SHELL := /bin/sh
.SHELLFLAGS := -eu -c

ENDPOINT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE ?= $(ENDPOINT_DIR)/.env
-include $(ENV_FILE)

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
DATABASE_REPOSITORY ?= $(ENDPOINT_DIR)/../database/target/m2
M2_DIR ?= $(ENDPOINT_DIR)/.cache/maven
M2_SETTINGS ?= $(HOME)/.m2/settings.xml
M2_SECURITY ?= $(HOME)/.m2/settings-security.xml
ARTIFACT_DIR := $(ENDPOINT_DIR)/target/artifacts
MAVEN_IMAGE ?= maven:3.9.11-eclipse-temurin-17
MAVEN_OFFLINE ?= false

COMPOSE = FAOSTAT_IMAGE="$(IMAGE)" ENDPOINT_VERSION="$(VERSION)" \
	FAOSTAT_VERSION="$(DATABASE_VERSION)" DUCKDB_JDBC_VERSION="$(DUCKDB_JDBC_VERSION)" \
	ONTOP_PORT="$(PORT)" \
	$(DOCKER) compose --project-directory "$(ENDPOINT_DIR)" -f "$(ENDPOINT_DIR)/docker-compose.yaml"

.PHONY: help show-config resolve build check test login publish up down logs ps

help: ## Show available targets (the default)
	@awk 'BEGIN { FS = ":.*## " } /^[[:alnum:]_.-]+:.*## / { printf "make %-24s # %s\n", $$1, $$2 }' "$(ENDPOINT_DIR)/Makefile"
	printf '\nOverrides: VERSION DATABASE_VERSION DUCKDB_JDBC_VERSION REPOSITORY IMAGE PORT GHCR_USER M2_DIR M2_SETTINGS M2_SECURITY DATABASE_REPOSITORY\n'

show-config: ## Show the selected image, artifact versions and host port
	@printf '%-22s %s\n' \
		IMAGE "$(IMAGE)" VERSION "$(VERSION)" DATABASE_VERSION "$(DATABASE_VERSION)" \
		DUCKDB_JDBC_VERSION "$(DUCKDB_JDBC_VERSION)" DATA_REPOSITORY_URL "$(DATA_REPOSITORY_URL)" PORT "$(PORT)" \
		DATABASE_REPOSITORY "$(DATABASE_REPOSITORY)" M2_DIR "$(M2_DIR)" M2_SETTINGS "$(M2_SETTINGS)" M2_SECURITY "$(M2_SECURITY)" \
		MAVEN_IMAGE "$(MAVEN_IMAGE)" MAVEN_OFFLINE "$(MAVEN_OFFLINE)"

resolve: ## Resolve from database/target/m2, the Maven cache or remote repositories
	cd "$(ENDPOINT_DIR)"
	mkdir -p "$(M2_DIR)/repository" "$(ARTIFACT_DIR)"
	cache_dir=$$(cd "$(M2_DIR)" && pwd)
	set --
	if [ -n "$(DATABASE_REPOSITORY)" ] && [ -d "$(DATABASE_REPOSITORY)" ]; then
		database_repository=$$(cd "$(DATABASE_REPOSITORY)" && pwd)
		set -- "$$@" --mount "type=bind,src=$$database_repository,dst=/database-repository,readonly" \
			--env FAOSTAT_LOCAL_REPOSITORY=true
	fi
	if [ -f "$(M2_SETTINGS)" ]; then
		set -- "$$@" --mount "type=bind,src=$(M2_SETTINGS),dst=/tmp/maven-home/.m2/settings.xml,readonly"
	fi
	if [ -f "$(M2_SECURITY)" ]; then
		set -- "$$@" --mount "type=bind,src=$(M2_SECURITY),dst=/tmp/maven-home/.m2/settings-security.xml,readonly"
	fi
	$(DOCKER) run --rm --user "$$(id -u):$$(id -g)" \
		--env HOME=/tmp/maven-home --env MAVEN_CONFIG=/tmp/maven-home/.m2 \
		--env MAVEN_OPTS=-Duser.home=/tmp/maven-home \
		--env FAOSTAT_REPOSITORY_URL="$(DATA_REPOSITORY_URL)" \
		--env FAOSTAT_VERSION="$(DATABASE_VERSION)" \
		--env DUCKDB_JDBC_VERSION="$(DUCKDB_JDBC_VERSION)" \
		--env MAVEN_OFFLINE="$(MAVEN_OFFLINE)" \
		--mount "type=bind,src=$$cache_dir/repository,dst=/maven-cache" \
		--mount "type=bind,src=$(ARTIFACT_DIR),dst=/artifacts" \
		--mount "type=bind,src=$(ENDPOINT_DIR)/build,dst=/opt/build,readonly" \
		--workdir /tmp --entrypoint /bin/sh "$$@" "$(MAVEN_IMAGE)" /opt/build/resolve-all.sh

build: resolve ## Resolve artifacts and build the endpoint image
	cd "$(ENDPOINT_DIR)"
	$(DOCKER) build --tag "$(IMAGE)" \
		--build-arg ENDPOINT_VERSION="$(VERSION)" \
		--build-arg FAOSTAT_VERSION="$(DATABASE_VERSION)" \
		--build-arg DUCKDB_JDBC_VERSION="$(DUCKDB_JDBC_VERSION)" .

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
