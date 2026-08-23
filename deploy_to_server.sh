#!/bin/bash
set -euo pipefail

PROJECT_DIR="$HOME/Code/training-etl"
SRC_DIR="$PROJECT_DIR/src"

SERVER="harrisserver"
SERVER_ETL_DIR="/opt/training/etl"

if [ ! -d "$SRC_DIR" ]; then
  echo "Local ETL source folder not found: $SRC_DIR"
  exit 1
fi

echo "Checking HarrisServer connection and ETL directory..."

if ! ssh "$SERVER" "test -d '$SERVER_ETL_DIR'"; then
  echo "Server ETL folder not found: $SERVER_ETL_DIR"
  echo "Create it on HarrisServer before deploying."
  exit 1
fi

echo "Deploying ETL files and scripts to HarrisServer..."

# -p preserves file permissions so backup_postgres.sh stays executable
rsync -avp --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  "$SRC_DIR/" "$SERVER:$SERVER_ETL_DIR/"

echo ""
echo "Deployment complete."
echo ""

ssh "$SERVER" "
  echo 'ETL folder:'
  ls -lah '$SERVER_ETL_DIR'
"