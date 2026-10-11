-- Manual additive DDL for the Structured Activity Data Contract.
-- This file is intentionally not applied by the ETL.

ALTER TABLE public.strava_activities
    ADD COLUMN IF NOT EXISTS start_at_utc timestamptz NULL,
    ADD COLUMN IF NOT EXISTS start_at_local timestamp without time zone NULL,
    ADD COLUMN IF NOT EXISTS timezone text NULL,
    ADD COLUMN IF NOT EXISTS utc_offset_seconds integer NULL,
    ADD COLUMN IF NOT EXISTS manual boolean NULL,
    ADD COLUMN IF NOT EXISTS trainer boolean NULL,
    ADD COLUMN IF NOT EXISTS commute boolean NULL,
    ADD COLUMN IF NOT EXISTS private boolean NULL,
    ADD COLUMN IF NOT EXISTS flagged boolean NULL,
    ADD COLUMN IF NOT EXISTS workout_type integer NULL,
    ADD COLUMN IF NOT EXISTS device_name text NULL,
    ADD COLUMN IF NOT EXISTS average_speed_mps double precision NULL,
    ADD COLUMN IF NOT EXISTS max_speed_mps double precision NULL,
    ADD COLUMN IF NOT EXISTS average_cadence double precision NULL,
    ADD COLUMN IF NOT EXISTS average_watts double precision NULL,
    ADD COLUMN IF NOT EXISTS weighted_average_watts double precision NULL,
    ADD COLUMN IF NOT EXISTS max_watts integer NULL,
    ADD COLUMN IF NOT EXISTS kilojoules double precision NULL,
    ADD COLUMN IF NOT EXISTS device_watts boolean NULL,
    ADD COLUMN IF NOT EXISTS relative_effort integer NULL,
    ADD COLUMN IF NOT EXISTS elevation_high_m double precision NULL,
    ADD COLUMN IF NOT EXISTS elevation_low_m double precision NULL,
    ADD COLUMN IF NOT EXISTS summary_observed_at timestamptz NULL;