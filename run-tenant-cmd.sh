#!/bin/bash
# Wrapper to run tenant management fully containerized via docker-compose
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-$(basename "$PWD" | tr '[:upper:]' '[:lower:]')}
docker compose -f docker-compose-multitenant.yml --profile tools run --rm -e COMPOSE_PROJECT_NAME="$PROJECT_NAME" tenant-manager "$@"
