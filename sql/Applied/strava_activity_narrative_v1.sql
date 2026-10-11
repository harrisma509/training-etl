-- Strava activity narrative storage, Slice 1.
-- Apply manually after reviewing the affected consumers.

ALTER TABLE public.strava_activities
    ADD COLUMN IF NOT EXISTS description text NULL,
    ADD COLUMN IF NOT EXISTS private_note text NULL,
    ADD COLUMN IF NOT EXISTS description_observed boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS private_note_observed boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS narrative_observed_at timestamptz NULL;

-- Verification after applying:
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'strava_activities'
  AND column_name IN (
      'description',
      'private_note',
      'description_observed',
      'private_note_observed',
      'narrative_observed_at'
  )
ORDER BY column_name;

-- Sanitized post-pilot validation without selecting narrative text.
SELECT
  activity_id,
  description_observed,
  description IS NOT NULL AS has_description,
  private_note_observed,
  private_note IS NOT NULL AS has_private_note,
  narrative_observed_at
FROM public.strava_activities
WHERE activity_id IN (20302298948, 19880001202, 18534000278)
ORDER BY activity_id;

-- Expected result after a successful pilot: invalid_narrative_rows = 0.
SELECT COUNT(*) AS invalid_narrative_rows
FROM public.strava_activities
WHERE (description IS NOT NULL AND NOT description_observed)
   OR (private_note IS NOT NULL AND NOT private_note_observed)
   OR (
     (description_observed OR private_note_observed)
     AND narrative_observed_at IS NULL
   );

