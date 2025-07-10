#!/bin/bash
# Stop servers for a specific environment

ENVIRONMENT=${1:-production}

case "$ENVIRONMENT" in
    "production")
        echo "Stopping production environment..."
        bd stop ib-stream || true
        bd stop ib-contracts || true
        ;;
    "development")
        echo "Stopping development environment..."
        bd stop ib-stream-dev || true
        bd stop ib-contracts-dev || true
        ;;
    "staging")
        echo "Stopping staging environment..."
        bd stop ib-stream-staging || true
        bd stop ib-contracts-staging || true
        ;;
    *)
        echo "Usage: $0 [production|development|staging]"
        echo "Stops all servers for the specified environment"
        exit 1
        ;;
esac

echo "$ENVIRONMENT environment stopped."