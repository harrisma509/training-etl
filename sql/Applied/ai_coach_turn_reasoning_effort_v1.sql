-- Persist the validated reasoning effort requested for each Coach turn.
-- Manual application only: review and execute through DBeaver.
-- Historical turns remain NULL and are not backfilled.

BEGIN;

ALTER TABLE public.coach_turn
    ADD COLUMN IF NOT EXISTS reasoning_effort_requested text NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.coach_turn'::regclass
          AND conname = 'coach_turn_reasoning_effort_requested_check'
    ) THEN
        ALTER TABLE public.coach_turn
            ADD CONSTRAINT coach_turn_reasoning_effort_requested_check
            CHECK (
                reasoning_effort_requested IS NULL
                OR reasoning_effort_requested IN ('none', 'low', 'medium', 'high')
            );
    END IF;
END $$;

COMMENT ON COLUMN public.coach_turn.reasoning_effort_requested IS
    'Validated reasoning effort requested from the provider for this turn; NULL means unavailable for historical turns.';

COMMIT;

-- Read-only verification:
-- SELECT reasoning_effort_requested, count(*)
-- FROM public.coach_turn
-- GROUP BY reasoning_effort_requested
-- ORDER BY reasoning_effort_requested;
