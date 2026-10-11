-- AI Coach settings persistence contract v1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This table stores non-secret, editable Coach controls only.

BEGIN;

-- Dedicated typed singleton table. The database bounds are intentionally broader
-- than the current application hard ceilings so future server policy can remain stricter.
CREATE TABLE public.ai_coach_settings (
    settings_id smallint NOT NULL,
    monthly_cost_limit_usd numeric(10, 2) DEFAULT 5.00 NOT NULL,
    max_turn_cost_usd numeric(10, 2) DEFAULT 0.25 NOT NULL,
    max_output_tokens integer DEFAULT 1200 NOT NULL,
    reasoning_effort text DEFAULT 'low' NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT ai_coach_settings_pkey PRIMARY KEY (settings_id),
    CONSTRAINT ai_coach_settings_singleton_check CHECK (settings_id = 1),
    CONSTRAINT ai_coach_settings_monthly_cost_check
        CHECK (
            monthly_cost_limit_usd >= 0.00
            AND monthly_cost_limit_usd <= 100.00
        ),
    CONSTRAINT ai_coach_settings_turn_cost_check
        CHECK (
            max_turn_cost_usd >= 0.01
            AND max_turn_cost_usd <= 5.00
        ),
    CONSTRAINT ai_coach_settings_output_tokens_check
        CHECK (
            max_output_tokens >= 1
            AND max_output_tokens <= 32000
        ),
    CONSTRAINT ai_coach_settings_reasoning_effort_check
        CHECK (reasoning_effort IN ('none', 'low', 'medium', 'high'))
);

COMMENT ON TABLE public.ai_coach_settings IS
    'Singleton non-secret editable settings for the Embedded AI Coach. Provider credentials and deployment settings remain outside the database.';
COMMENT ON COLUMN public.ai_coach_settings.settings_id IS
    'Singleton identifier. The only supported value is 1.';
COMMENT ON COLUMN public.ai_coach_settings.monthly_cost_limit_usd IS
    'Application-recorded monthly cost ceiling in USD. Database range 0.00 through 100.00 prevents absurd values; application hard ceilings remain authoritative.';
COMMENT ON COLUMN public.ai_coach_settings.max_turn_cost_usd IS
    'Maximum estimated cost allowed for one Coach turn in USD. Database range 0.01 through 5.00 prevents absurd values; application hard ceilings remain authoritative.';
COMMENT ON COLUMN public.ai_coach_settings.max_output_tokens IS
    'Maximum output tokens requested for a normal Coach turn. Database range 1 through 10000 prevents absurd values; application hard ceilings remain authoritative.';
COMMENT ON COLUMN public.ai_coach_settings.reasoning_effort IS
    'Normal Coach reasoning effort. Supported values are none, low, medium, and high.';
COMMENT ON COLUMN public.ai_coach_settings.updated_at IS
    'Timestamp of the most recent settings update. Future application updates should set this explicitly with now().';

-- Seed the one supported row without overwriting any manually reviewed value.
INSERT INTO public.ai_coach_settings (
    settings_id,
    monthly_cost_limit_usd,
    max_turn_cost_usd,
    max_output_tokens,
    reasoning_effort
)
VALUES (1, 5.00, 0.25, 1200, 'low')
ON CONFLICT (settings_id) DO NOTHING;

-- Read-only verification queries for manual review after execution.
SELECT
    settings_id,
    monthly_cost_limit_usd,
    max_turn_cost_usd,
    max_output_tokens,
    reasoning_effort,
    updated_at
FROM public.ai_coach_settings
ORDER BY settings_id;

SELECT
    count(*) AS singleton_row_count,
    bool_and(settings_id = 1) AS singleton_id_is_valid
FROM public.ai_coach_settings;

COMMIT;
