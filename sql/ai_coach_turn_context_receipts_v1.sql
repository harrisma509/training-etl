-- AI Coach Context Receipt persistence contract v1.1.
-- Manual DBeaver execution only: review this script and execute it manually.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This script intentionally has no BEGIN or COMMIT wrapper.
-- The receipt is an optional immutable snapshot of bounded context assembled for
-- one Coach turn. It is not a prompt archive, provider payload log, or debug log.

CREATE TABLE public.ai_coach_turn_context_receipts (
    coach_turn_id bigint NOT NULL,
    receipt_version smallint DEFAULT 1 NOT NULL,
    receipt_json jsonb NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT ai_coach_turn_context_receipts_pkey PRIMARY KEY (coach_turn_id),
    CONSTRAINT ai_coach_turn_context_receipts_receipt_version_check
        CHECK (receipt_version >= 1),
    CONSTRAINT ai_coach_turn_context_receipts_receipt_json_object_check
        CHECK (jsonb_typeof(receipt_json) = 'object')
);

ALTER TABLE public.ai_coach_turn_context_receipts
    ADD CONSTRAINT ai_coach_turn_context_receipts_turn_fkey
    FOREIGN KEY (coach_turn_id)
    REFERENCES public.coach_turn(coach_turn_id)
    ON DELETE CASCADE;

COMMENT ON TABLE public.ai_coach_turn_context_receipts IS
    'Optional immutable, versioned snapshot of bounded Coach context assembled for one turn. Not a prompt archive, provider payload log, or debug log.';
COMMENT ON COLUMN public.ai_coach_turn_context_receipts.coach_turn_id IS
    'One-to-one reference to the Coach turn whose assembled context this receipt records. The primary key enforces at most one receipt per turn.';
COMMENT ON COLUMN public.ai_coach_turn_context_receipts.receipt_version IS
    'Version of the receipt JSON document shape. V1.1 application writes use version 1.';
COMMENT ON COLUMN public.ai_coach_turn_context_receipts.receipt_json IS
    'Required bounded allowlisted receipt object. It excludes full memory text, prompts, raw provider payloads, SQL, credentials, routing scores, and full Training Intelligence context.';
COMMENT ON COLUMN public.ai_coach_turn_context_receipts.created_at IS
    'Creation timestamp for immutable application evidence. There is intentionally no updated_at column or trigger in V1.1.';

-- Read-only verification queries for manual review after execution.
SELECT to_regclass('public.ai_coach_turn_context_receipts') IS NOT NULL AS table_exists;

SELECT count(*) AS total_receipt_count
FROM public.ai_coach_turn_context_receipts;

SELECT receipt_version, count(*) AS receipt_count
FROM public.ai_coach_turn_context_receipts
GROUP BY receipt_version
ORDER BY receipt_version;

SELECT count(*) AS non_object_receipt_json_count
FROM public.ai_coach_turn_context_receipts
WHERE jsonb_typeof(receipt_json) <> 'object';

SELECT count(*) AS orphan_receipt_count
FROM public.ai_coach_turn_context_receipts r
LEFT JOIN public.coach_turn t ON t.coach_turn_id = r.coach_turn_id
WHERE t.coach_turn_id IS NULL;

SELECT max(char_length(receipt_json::text)) AS maximum_serialized_receipt_characters
FROM public.ai_coach_turn_context_receipts;

SELECT
    count(*) FILTER (
        WHERE jsonb_typeof(receipt_json -> 'selected_memories') = 'array'
          AND jsonb_array_length(receipt_json -> 'selected_memories') > 0
    ) AS receipts_with_selected_memories,
    count(*) FILTER (
        WHERE jsonb_typeof(receipt_json -> 'selected_memories') = 'array'
          AND jsonb_array_length(receipt_json -> 'selected_memories') = 0
    ) AS receipts_without_selected_memories
FROM public.ai_coach_turn_context_receipts;
