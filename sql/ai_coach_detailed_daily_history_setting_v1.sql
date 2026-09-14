-- AI Coach detailed daily-history setting additive migration v1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This migration adds one bounded, non-secret Coach setting to the existing singleton.

BEGIN;

ALTER TABLE public.ai_coach_settings
    ADD COLUMN detailed_daily_history_days integer DEFAULT 28 NOT NULL;

ALTER TABLE public.ai_coach_settings
    ADD CONSTRAINT ai_coach_settings_detailed_daily_history_days_check
    CHECK (
        detailed_daily_history_days >= 7
        AND detailed_daily_history_days <= 56
    );

-- Read-only verification queries for manual review after execution.
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'ai_coach_settings'
  AND column_name = 'detailed_daily_history_days';

SELECT
    constraint_name,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'public.ai_coach_settings'::regclass
  AND conname = 'ai_coach_settings_detailed_daily_history_days_check';

SELECT
    settings_id,
    detailed_daily_history_days
FROM public.ai_coach_settings
WHERE settings_id = 1;

SELECT
    count(*) AS singleton_row_count,
    bool_and(settings_id = 1) AS singleton_id_is_valid
FROM public.ai_coach_settings;

COMMIT;
