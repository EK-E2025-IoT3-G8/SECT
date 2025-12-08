#!/bin/bash
BACKUP_DIR="/var/backups/psql"
DB_NAME="" # Update to db_name from script.py
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE=$(BACKUP_DIR)/$(DB_NAME)_backup_$(TIME_STAMP).sql

pg_dump -U postgres "$DB_NAME" > "$FILE"

scp "$FILE" device:/var/backup/sql/