-- AI Coach Durable Memories persistence contract v1.1.
-- Manual DBeaver execution only: review this script and execute it manually.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This script intentionally has no BEGIN or COMMIT wrapper.
-- Durable Memories are manually curated background facts, not policy, current
-- Training Intelligence metrics, conversation history, or provider memory.

CREATE TABLE public.ai_coach_memories (
    memory_id bigint GENERATED ALWAYS AS IDENTITY (
        INCREMENT BY 1
        MINVALUE 1
        MAXVALUE 9223372036854775807
        START 1
        CACHE 1
        NO CYCLE
    ) NOT NULL,
    memory_type text NOT NULL,
    title text NOT NULL,
    memory_text text NOT NULL,
    applies_to text[] NOT NULL,
    priority text DEFAULT 'normal' NOT NULL,
    effective_date date,
    expires_at timestamptz,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT ai_coach_memories_memory_type_check
        CHECK (memory_type = ANY (ARRAY[
            'medical'::text,
            'safety'::text,
            'training_goal'::text,
            'schedule'::text,
            'event'::text,
            'equipment'::text,
            'preference'::text,
            'lesson_learned'::text
        ])),
    CONSTRAINT ai_coach_memories_title_not_blank CHECK (btrim(title) <> ''::text),
    CONSTRAINT ai_coach_memories_title_length_check CHECK (char_length(title) <= 120),
    CONSTRAINT ai_coach_memories_memory_text_not_blank CHECK (btrim(memory_text) <> ''::text),
    CONSTRAINT ai_coach_memories_memory_text_length_check CHECK (char_length(memory_text) <= 1000),
    CONSTRAINT ai_coach_memories_applies_to_not_empty CHECK (cardinality(applies_to) > 0),
    CONSTRAINT ai_coach_memories_applies_to_no_nulls CHECK (array_position(applies_to, NULL::text) IS NULL),
    CONSTRAINT ai_coach_memories_applies_to_allowed_values_check
        CHECK (applies_to <@ ARRAY[
            'all_training'::text,
            'planning'::text,
            'recovery'::text,
            'strength'::text,
            'weight'::text,
            'mtb'::text,
            'emtb'::text,
            'bike_park'::text,
            'gravel'::text,
            'skiing'::text
        ]),
    CONSTRAINT ai_coach_memories_priority_check
        CHECK (priority = ANY (ARRAY['critical'::text, 'high'::text, 'normal'::text])),
    CONSTRAINT ai_coach_memories_date_order_check
        CHECK (
            effective_date IS NULL
            OR expires_at IS NULL
            OR effective_date <= (expires_at AT TIME ZONE 'America/Denver')::date
        ),
    CONSTRAINT ai_coach_memories_pkey PRIMARY KEY (memory_id)
);

COMMENT ON TABLE public.ai_coach_memories IS
    'Manually curated Durable Memories for AI Coach. These selected background facts do not replace product policy, current authoritative Training Intelligence, clinician guidance, or bounded conversation context. Deactivation is the application removal mechanism.';
COMMENT ON COLUMN public.ai_coach_memories.memory_id IS
    'Stable internal identifier for management and deterministic tie-breaking. This identifier is not included in the model-facing memory body.';
COMMENT ON COLUMN public.ai_coach_memories.memory_type IS
    'Required lowercase controlled type: medical, safety, training_goal, schedule, event, equipment, preference, or lesson_learned.';
COMMENT ON COLUMN public.ai_coach_memories.title IS
    'Short human-readable management label, limited to 120 characters. Future application validation normalizes and trims it.';
COMMENT ON COLUMN public.ai_coach_memories.memory_text IS
    'Standalone human-authored fact with relational context, limited to 1,000 characters. Do not store HTML, compiled prompt text, secrets, SQL, or provider configuration.';
COMMENT ON COLUMN public.ai_coach_memories.applies_to IS
    'One or more lowercase controlled applicability scopes. Database checks enforce nonempty, non-NULL, approved values; the future application rejects duplicate scopes.';
COMMENT ON COLUMN public.ai_coach_memories.priority IS
    'Required lowercase controlled priority: critical, high, or normal. Defaults to normal.';
COMMENT ON COLUMN public.ai_coach_memories.effective_date IS
    'Optional local-calendar start date. A memory is eligible only when this is NULL or on/before the request local date.';
COMMENT ON COLUMN public.ai_coach_memories.expires_at IS
    'Optional expiration instant. A memory is eligible only when this is NULL or later than request generation. Date-order validation converts this instant to America/Denver.';
COMMENT ON COLUMN public.ai_coach_memories.is_active IS
    'Application-managed active flag. Deactivation replaces hard delete in V1.1; expiration does not change this flag.';
COMMENT ON COLUMN public.ai_coach_memories.created_at IS
    'Creation timestamp.';
COMMENT ON COLUMN public.ai_coach_memories.updated_at IS
    'Most recent application update timestamp. Future updates set this explicitly with now(); no trigger is part of this contract.';

-- Read-only verification queries for manual review after execution.
SELECT to_regclass('public.ai_coach_memories') IS NOT NULL AS table_exists;

SELECT
    count(*) AS total_memory_count,
    count(*) FILTER (WHERE is_active) AS active_memory_count,
    count(*) FILTER (
        WHERE is_active
          AND (effective_date IS NULL OR effective_date <= (now() AT TIME ZONE 'America/Denver')::date)
          AND (expires_at IS NULL OR expires_at > now())
    ) AS active_eligible_count,
    count(*) FILTER (WHERE NOT is_active) AS inactive_count,
    count(*) FILTER (WHERE effective_date > (now() AT TIME ZONE 'America/Denver')::date) AS future_effective_count,
    count(*) FILTER (WHERE expires_at IS NOT NULL AND expires_at <= now()) AS expired_count
FROM public.ai_coach_memories;

SELECT
    memory_id,
    memory_type,
    title,
    memory_text,
    applies_to,
    priority,
    effective_date,
    expires_at,
    is_active
FROM public.ai_coach_memories
WHERE memory_type IS NULL
   OR memory_type NOT IN ('medical', 'safety', 'training_goal', 'schedule', 'event', 'equipment', 'preference', 'lesson_learned')
   OR title IS NULL
   OR btrim(title) = ''
   OR char_length(title) > 120
   OR memory_text IS NULL
   OR btrim(memory_text) = ''
   OR char_length(memory_text) > 1000
   OR applies_to IS NULL
   OR cardinality(applies_to) = 0
   OR array_position(applies_to, NULL::text) IS NOT NULL
   OR NOT (applies_to <@ ARRAY['all_training', 'planning', 'recovery', 'strength', 'weight', 'mtb', 'emtb', 'bike_park', 'gravel', 'skiing']::text[])
   OR priority IS NULL
   OR priority NOT IN ('critical', 'high', 'normal')
   OR (effective_date IS NOT NULL AND expires_at IS NOT NULL AND effective_date > (expires_at AT TIME ZONE 'America/Denver')::date);

SELECT
    count(*) FILTER (
        WHERE memory_type IS NULL
           OR memory_type NOT IN ('medical', 'safety', 'training_goal', 'schedule', 'event', 'equipment', 'preference', 'lesson_learned')
           OR title IS NULL
           OR btrim(title) = ''
           OR char_length(title) > 120
           OR memory_text IS NULL
           OR btrim(memory_text) = ''
           OR char_length(memory_text) > 1000
           OR applies_to IS NULL
           OR cardinality(applies_to) = 0
           OR array_position(applies_to, NULL::text) IS NOT NULL
           OR NOT (applies_to <@ ARRAY['all_training', 'planning', 'recovery', 'strength', 'weight', 'mtb', 'emtb', 'bike_park', 'gravel', 'skiing']::text[])
           OR priority IS NULL
           OR priority NOT IN ('critical', 'high', 'normal')
           OR (effective_date IS NOT NULL AND expires_at IS NOT NULL AND effective_date > (expires_at AT TIME ZONE 'America/Denver')::date)
    ) AS invalid_row_count,
    max(char_length(title)) AS maximum_title_characters,
    max(char_length(memory_text)) AS maximum_memory_characters
FROM public.ai_coach_memories;