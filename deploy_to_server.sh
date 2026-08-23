#!/bin/bash
set -euo pipefail

PROJECT_DIR="$HOME/Code/training-etl"
SRC_DIR="$PROJECT_DIR/src"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.server.yml"
DOCKERFILE="$PROJECT_DIR/Dockerfile"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"

SERVER="harrisserver"
SERVER_ETL_DIR="/opt/training/etl"
SERVER_BUILD_DIR="/opt/training/etl-build"
SERVER_COMPOSE_FILE="/opt/training/docker-compose.server.yml"

for path in "$SRC_DIR" "$COMPOSE_FILE" "$DOCKERFILE" "$REQUIREMENTS_FILE"; do
  if [ ! -e "$path" ]; then
    echo "Required local path not found: $path"
    exit 1
  fi
done

echo "Checking HarrisServer connection and deployment directories..."

if ! ssh "$SERVER" "test -d '$SERVER_ETL_DIR' && test -d '$SERVER_BUILD_DIR'"; then
  echo "Required server directories are missing."
  echo "Expected: $SERVER_ETL_DIR and $SERVER_BUILD_DIR"
  exit 1
fi

echo "Deploying ETL files and scripts..."

rsync -avp --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  "$SRC_DIR/" "$SERVER:$SERVER_ETL_DIR/"

echo "Deploying Docker build files..."

rsync -avp \
  "$DOCKERFILE" \
  "$REQUIREMENTS_FILE" \
  "$SERVER:$SERVER_BUILD_DIR/"

echo "Deploying server Compose file..."

rsync -avp \
  "$COMPOSE_FILE" \
  "$SERVER:$SERVER_COMPOSE_FILE"

echo
echo "Deployment complete."
echo

ssh "$SERVER" "
  echo 'ETL folder:'
  ls -lah '$SERVER_ETL_DIR'
  echo
  echo 'Docker build files:'
  ls -lah '$SERVER_BUILD_DIR/Dockerfile' '$SERVER_BUILD_DIR/requirements.txt'
  echo
  echo 'Compose file:'
  ls -lah '$SERVER_COMPOSE_FILE'
"

echo "Containers were not recreated or restarted."
