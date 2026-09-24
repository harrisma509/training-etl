-- DESTRUCTIVE rollback for Slice 1.
-- Use only before meaningful narrative data is retained.

ALTER TABLE public.strava_activities
    DROP COLUMN IF EXISTS description,
    DROP COLUMN IF EXISTS private_note,
    DROP COLUMN IF EXISTS description_observed,
    DROP COLUMN IF EXISTS private_note_observed,
    DROP COLUMN IF EXISTS narrative_observed_at;