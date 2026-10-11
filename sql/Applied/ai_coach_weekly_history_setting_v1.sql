-- AI Coach weekly-history setting additive migration v1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This migration adds one non-secret Coach setting to the existing singleton.

BEGIN;

ALTER TABLE public.ai_coach_settings
    ADD COLUMN weekly_history_rows integer DEFAULT 26 NOT NULL;

COMMIT;

-- Read-only verification queries for manual review after execution.
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'ai_coach_settings'
  AND column_name = 'weekly_history_rows';

SELECT
    settings_id,
    weekly_history_rows
FROM public.ai_coach_settings
WHERE settings_id = 1;

SELECT
    count(*) AS singleton_row_count,
    bool_and(settings_id = 1) AS singleton_id_is_valid
FROM public.ai_coach_settings;