#!/bin/bash
# Wrapper to run tenant management fully containerized via docker-compose
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-$(basename "$PWD" | tr '[:upper:]' '[:lower:]')}
# Pass the absolute working directory to the container so docker compose can resolve paths correctly
docker compose -f docker-compose-multitenant.yml --profile tools run --rm -e COMPOSE_PROJECT_NAME="$PROJECT_NAME" -e HOST_WORKDIR="$PWD" tenant-manager "$@"
