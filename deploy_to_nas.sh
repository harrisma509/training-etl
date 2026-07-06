#!/bin/bash
set -euo pipefail

PROJECT_DIR="$HOME/Code/training-etl"
SRC_DIR="$PROJECT_DIR/src"
CONFIG_DIR="$PROJECT_DIR/config"

NAS_ROOT="/Volumes/docker/training"
NAS_ETL_DIR="$NAS_ROOT/etl"
NAS_CONFIG_DIR="$NAS_ROOT/config"

if [ ! -d "$NAS_ETL_DIR" ]; then
  echo "NAS ETL folder not found: $NAS_ETL_DIR"
  echo "Mount smb://192.168.1.188/docker first."
  exit 1
fi

if [ ! -d "$NAS_CONFIG_DIR" ]; then
  echo "NAS config folder not found: $NAS_CONFIG_DIR"
  echo "Mount smb://192.168.1.188/docker first."
  exit 1
fi

echo "Deploying Python files to NAS..."
rsync -av --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  "$SRC_DIR/" "$NAS_ETL_DIR/"

echo "Deploying non-secret config files to NAS..."
rsync -av \
  --exclude ".DS_Store" \
  --exclude "*.env" \
  --exclude "strava.env" \
  "$CONFIG_DIR/"*.csv "$NAS_CONFIG_DIR/" 2>/dev/null || true

echo "Deploy complete."

echo ""
echo "ETL folder:"
ls -lah "$NAS_ETL_DIR"

echo ""
echo "Config CSV files:"
ls -lah "$NAS_CONFIG_DIR"/*.csv 2>/dev/null || echo "No CSV config files found."