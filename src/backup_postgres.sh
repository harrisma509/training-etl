cat << 'EOF' | sudo tee /opt/training/backup_postgres.sh
#!/bin/bash
set -e

BACKUP_DIR="/mnt/harrisnas/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ENV_FILE="/etc/training/.env"

# Ensure target directory exists
mkdir -p "$BACKUP_DIR"

# Extract DB credentials
if [ -f "$ENV_FILE" ]; then
    export PGPASSWORD=$(grep DB_PASSWORD "$ENV_FILE" | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    DB_USER=$(grep DB_USER "$ENV_FILE" | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    DB_NAME=$(grep DB_NAME "$ENV_FILE" | cut -d '=' -f2 | tr -d '"' | tr -d "'")
else
    DB_USER="training_app"
    DB_NAME="training"
fi

# Execute dump
pg_dump -U "$DB_USER" -h 127.0.0.1 "$DB_NAME" | gzip > "$BACKUP_DIR/pg_${DB_NAME}_${TIMESTAMP}.sql.gz"

# Clean up exported env
unset PGPASSWORD

# Keep only the last 14 days of backups
find "$BACKUP_DIR" -name "pg_${DB_NAME}_*.sql.gz" -mtime +14 -delete

echo "Backup complete: $BACKUP_DIR/pg_${DB_NAME}_${TIMESTAMP}.sql.gz"
EOF

sudo chmod +x /opt/training/backup_postgres.sh