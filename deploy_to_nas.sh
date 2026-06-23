#!/bin/bash
set -euo pipefail

SRC_DIR="$HOME/Code/training-etl/src"
NAS_ETL_DIR="/Volumes/docker/training/etl"

if [ ! -d "$NAS_ETL_DIR" ]; then
  echo "NAS deploy folder not found: $NAS_ETL_DIR"
  echo "Mount smb://192.168.1.188/docker first."
  exit 1
fi

echo "Deploying Python files to NAS..."
rsync -av --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  "$SRC_DIR/" "$NAS_ETL_DIR/"

echo "Deploy complete:"
ls -lah "$NAS_ETL_DIR"