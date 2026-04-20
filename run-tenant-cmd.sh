#!/bin/bash
# Wrapper to run tenant management fully containerized via docker-compose
docker-compose -f docker-compose-multitenant.yml --profile tools run --rm tenant-manager "$@"
