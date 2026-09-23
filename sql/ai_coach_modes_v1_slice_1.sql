-- AI Coach Modes V1 Slice 1 additive migration.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- Existing sessions and turns receive the Training Coach default.

BEGIN;

ALTER TABLE public.coach_session
    ADD COLUMN current_mode text DEFAULT 'training' NOT NULL;

ALTER TABLE public.coach_session
    ADD CONSTRAINT coach_session_current_mode_check
    CHECK (current_mode IN ('training', 'conversational'));

ALTER TABLE public.coach_turn
    ADD COLUMN coach_mode text DEFAULT 'training' NOT NULL;

ALTER TABLE public.coach_turn
    ADD CONSTRAINT coach_turn_coach_mode_check
    CHECK (coach_mode IN ('training', 'conversational'));

COMMIT;

-- Read-only verification queries for manual review after execution.
SELECT table_name, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND ((table_name = 'coach_session' AND column_name = 'current_mode')
    OR (table_name = 'coach_turn' AND column_name = 'coach_mode'))
ORDER BY table_name, column_name;

SELECT conrelid::regclass AS table_name,
       conname AS constraint_name,
       pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conname IN ('coach_session_current_mode_check', 'coach_turn_coach_mode_check')
ORDER BY conname;

SELECT 'coach_session' AS table_name, current_mode AS mode, count(*) AS row_count
FROM public.coach_session
GROUP BY current_mode
UNION ALL
SELECT 'coach_turn' AS table_name, coach_mode AS mode, count(*) AS row_count
FROM public.coach_turn
GROUP BY coach_mode
ORDER BY table_name, mode;

-- Rollback (destructive for mode data created after this migration):
-- BEGIN;
-- ALTER TABLE public.coach_turn DROP CONSTRAINT coach_turn_coach_mode_check;
-- ALTER TABLE public.coach_turn DROP COLUMN coach_mode;
-- ALTER TABLE public.coach_session DROP CONSTRAINT coach_session_current_mode_check;
-- ALTER TABLE public.coach_session DROP COLUMN current_mode;
-- COMMIT;