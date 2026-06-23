# Training ETL

Python ETL project for moving Strava API logic out of Excel/VBA.

## Current scope

- Pull recent Strava activities
- Write preview JSON
- No database yet
- No desktop Excel dependency

## Security rules

- Do not commit real Strava tokens
- Do not commit database passwords
- Do not mount NAS family/cloud/photo/finance folders
- NAS runtime folders are limited to /docker/training