# Training ETL

Python ETL project for the Training Dashboard.

## Current scope

- Pull recent Strava activities
- Build daily and weekly training summary data
- Write dashboard source data to Postgres
- Support weekly audit computation
- Maintain gear-related database helpers
- Store schema/reference SQL for the training database
- Avoid desktop Excel dependency for app runtime

## Repo boundary

This repo owns:

- Strava ingestion
- ETL builders
- database writes
- schema SQL
- weekly audit computation
- future service log import and service status builders

The separate `training-web` repo owns:

- FastAPI web app
- browser dashboard UI
- API routes
- NAS web deployment
- static frontend files

Schema changes in this repo must be validated against the web app before deploy.

## Security rules

- Do not commit real Strava tokens
- Do not commit database passwords
- Do not commit `.env` files
- Do not mount NAS family/cloud/photo/finance folders
- NAS runtime folders are limited to `/docker/training`
- Do not expose raw Strava JSON or secrets in logs or dashboard APIs

## Validation

For ETL changes:

1. Run syntax checks on touched Python files.
2. Run the relevant ETL script locally or in the intended runtime.
3. Confirm database writes land in the expected tables.
4. Confirm the web dashboard still loads affected tabs.
5. Confirm no token, credential, or raw secret-like value is logged.