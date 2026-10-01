-- DESTRUCTIVE rollback for the Structured Activity Data Contract.
-- Use only before meaningful structured activity data is retained.

ALTER TABLE public.strava_activities
    DROP COLUMN IF EXISTS start_at_utc,
    DROP COLUMN IF EXISTS start_at_local,
    DROP COLUMN IF EXISTS timezone,
    DROP COLUMN IF EXISTS utc_offset_seconds,
    DROP COLUMN IF EXISTS manual,
    DROP COLUMN IF EXISTS trainer,
    DROP COLUMN IF EXISTS commute,
    DROP COLUMN IF EXISTS private,
    DROP COLUMN IF EXISTS flagged,
    DROP COLUMN IF EXISTS workout_type,
    DROP COLUMN IF EXISTS device_name,
    DROP COLUMN IF EXISTS average_speed_mps,
    DROP COLUMN IF EXISTS max_speed_mps,
    DROP COLUMN IF EXISTS average_cadence,
    DROP COLUMN IF EXISTS average_watts,
    DROP COLUMN IF EXISTS weighted_average_watts,
    DROP COLUMN IF EXISTS max_watts,
    DROP COLUMN IF EXISTS kilojoules,
    DROP COLUMN IF EXISTS device_watts,
    DROP COLUMN IF EXISTS relative_effort,
    DROP COLUMN IF EXISTS elevation_high_m,
    DROP COLUMN IF EXISTS elevation_low_m,
    DROP COLUMN IF EXISTS summary_observed_at;