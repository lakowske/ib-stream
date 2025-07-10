#!/bin/bash
# Migration script for switching between environments safely

set -e

FROM_ENV=${1:-production}
TO_ENV=${2:-staging}
BACKUP=${3:-true}

echo "Migration from $FROM_ENV to $TO_ENV"
echo "Backup enabled: $BACKUP"

# Validate environments
if [[ ! "$FROM_ENV" =~ ^(production|development|staging)$ ]]; then
    echo "Invalid FROM environment: $FROM_ENV"
    exit 1
fi

if [[ ! "$TO_ENV" =~ ^(production|development|staging)$ ]]; then
    echo "Invalid TO environment: $TO_ENV"
    exit 1
fi

# Check if config files exist
FROM_CONFIG="config/$FROM_ENV.env"
TO_CONFIG="config/$TO_ENV.env"

if [ ! -f "$FROM_CONFIG" ]; then
    echo "Configuration file not found: $FROM_CONFIG"
    exit 1
fi

if [ ! -f "$TO_CONFIG" ]; then
    echo "Configuration file not found: $TO_CONFIG"
    exit 1
fi

# Get storage paths from config files
FROM_STORAGE=$(grep "IB_STREAM_STORAGE_PATH" "$FROM_CONFIG" | cut -d'=' -f2)
TO_STORAGE=$(grep "IB_STREAM_STORAGE_PATH" "$TO_CONFIG" | cut -d'=' -f2)

echo "Storage migration: $FROM_STORAGE -> $TO_STORAGE"

# Create backup if requested
if [ "$BACKUP" = "true" ] && [ -d "$FROM_STORAGE" ]; then
    BACKUP_NAME="${FROM_STORAGE}-backup-$(date +%Y%m%d-%H%M%S)"
    echo "Creating backup: $BACKUP_NAME"
    cp -r "$FROM_STORAGE" "$BACKUP_NAME"
    echo "Backup created: $BACKUP_NAME"
fi

# Stop source environment
echo "Stopping $FROM_ENV environment..."
./scripts/stop-environment.sh "$FROM_ENV"

# Wait for graceful shutdown
sleep 2

# Create storage directory if it doesn't exist
if [ ! -d "$TO_STORAGE" ]; then
    echo "Creating storage directory: $TO_STORAGE"
    mkdir -p "$TO_STORAGE"/{json,protobuf}
fi

# Copy data if migrating to a new storage location
if [ "$FROM_STORAGE" != "$TO_STORAGE" ] && [ -d "$FROM_STORAGE" ]; then
    echo "Copying data from $FROM_STORAGE to $TO_STORAGE..."
    rsync -av "$FROM_STORAGE/" "$TO_STORAGE/"
    echo "Data copy completed"
fi

# Start target environment
echo "Starting $TO_ENV environment..."
case "$TO_ENV" in
    "production")
        ./scripts/start-production.sh
        ;;
    "development")
        ./scripts/start-development.sh
        ;;
    "staging")
        ./scripts/start-staging.sh
        ;;
esac

echo "Migration completed successfully!"
echo ""
echo "Verify the migration:"
case "$TO_ENV" in
    "production")
        echo "  curl -s http://localhost:8001/health | jq ."
        echo "  curl -s http://localhost:8000/health | jq ."
        ;;
    "development")
        echo "  curl -s http://localhost:8101/health | jq ."
        echo "  curl -s http://localhost:8100/health | jq ."
        ;;
    "staging")
        echo "  curl -s http://localhost:8201/health | jq ."
        echo "  curl -s http://localhost:8200/health | jq ."
        ;;
esac