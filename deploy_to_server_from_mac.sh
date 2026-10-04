#!/bin/bash
set -euo pipefail

PROJECT_DIR="$HOME/Code/training-etl"
SRC_DIR="$PROJECT_DIR/src"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.server.yml"
DOCKERFILE="$PROJECT_DIR/Dockerfile"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"
ARCHIVE_NAME="training-etl-deploy.tar.gz"
LOCAL_ARCHIVE="${TMPDIR:-/tmp}/${ARCHIVE_NAME}"
REMOTE_ARCHIVE="/tmp/${ARCHIVE_NAME}"
REMOTE_STAGE="/tmp/training-etl-deploy"
DRY_RUN=false

if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [--dry-run]"
  exit 2
fi
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
elif [ "$#" -eq 1 ]; then
  echo "Usage: $0 [--dry-run]"
  exit 2
fi

cleanup() {
  rm -f "$LOCAL_ARCHIVE"
}
trap cleanup EXIT

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

cd "$PROJECT_DIR"

if [ -n "$(git status --porcelain)" ]; then
  echo "Deployment requires a clean Git working tree."
  exit 1
fi

REVISION="$(git rev-parse HEAD)"
UPSTREAM_REVISION="$(git rev-parse --verify '@{u}')"
if [[ ! "$REVISION" =~ ^[0-9a-f]{40}$ || "$REVISION" != "$UPSTREAM_REVISION" ]]; then
  echo "Deployment requires HEAD to equal its configured upstream revision."
  exit 1
fi

REMOTE_COMMAND="set -e; rm -rf '$REMOTE_STAGE'; mkdir -p '$REMOTE_STAGE'; tar -xzf '$REMOTE_ARCHIVE' -C '$REMOTE_STAGE'; cp -a '$REMOTE_STAGE/src/.' '$SERVER_ETL_DIR/'; cp '$REMOTE_STAGE/Dockerfile' '$REMOTE_STAGE/requirements.txt' '$SERVER_BUILD_DIR/'; cp '$REMOTE_STAGE/docker-compose.server.yml' '$SERVER_COMPOSE_FILE'; rm -rf '$REMOTE_STAGE'; rm -f '$REMOTE_ARCHIVE'; echo 'Deployment complete.'"

echo "Packaging training-etl revision $REVISION..."
rm -f "$LOCAL_ARCHIVE"
tar -czf "$LOCAL_ARCHIVE" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude=".DS_Store" \
  src Dockerfile requirements.txt docker-compose.server.yml

if [ "$DRY_RUN" = true ]; then
  echo "Dry run complete. Archive contents:"
  tar -tzf "$LOCAL_ARCHIVE"
  echo "No files were uploaded or changed."
  exit 0
fi

echo "Checking HarrisServer connection and deployment directories..."

if ! ssh "$SERVER" "test -d '$SERVER_ETL_DIR' && test -d '$SERVER_BUILD_DIR'"; then
  echo "Required server directories are missing."
  echo "Expected: $SERVER_ETL_DIR and $SERVER_BUILD_DIR"
  exit 1
fi

echo "Uploading archive..."
scp -o BatchMode=yes "$LOCAL_ARCHIVE" "$SERVER:$REMOTE_ARCHIVE"

echo "Extracting files on HarrisServer..."
ssh -o BatchMode=yes "$SERVER" "$REMOTE_COMMAND"

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

echo "No containers were rebuilt or restarted by this script."
echo "Apply the documented restart, recreation, or rebuild action for the changed artifact."
