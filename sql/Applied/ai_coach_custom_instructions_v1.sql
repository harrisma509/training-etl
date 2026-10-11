-- AI Coach Custom Instructions persistence contract v1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This script intentionally has no BEGIN or COMMIT wrapper.
-- The database stores bounded durable coaching instructions, not secrets, memories,
-- weekly plans, current injuries, or recalculated Training Intelligence metrics.

CREATE TABLE public.ai_coach_custom_instructions (
    instructions_id smallint NOT NULL,
    coaching_priorities text DEFAULT '' NOT NULL,
    safety_progression_rules text DEFAULT '' NOT NULL,
    training_approach text DEFAULT '' NOT NULL,
    recovery_adjustment_rules text DEFAULT '' NOT NULL,
    communication_style text DEFAULT '' NOT NULL,
    planning_preferences text DEFAULT '' NOT NULL,
    other_instructions text DEFAULT '' NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT ai_coach_custom_instructions_pkey PRIMARY KEY (instructions_id),
    CONSTRAINT ai_coach_custom_instructions_singleton_check CHECK (instructions_id = 1),
    CONSTRAINT ai_coach_custom_instructions_coaching_priorities_length_check
        CHECK (char_length(coaching_priorities) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_safety_progression_rules_length_check
        CHECK (char_length(safety_progression_rules) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_training_approach_length_check
        CHECK (char_length(training_approach) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_recovery_adjustment_rules_length_check
        CHECK (char_length(recovery_adjustment_rules) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_communication_style_length_check
        CHECK (char_length(communication_style) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_planning_preferences_length_check
        CHECK (char_length(planning_preferences) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_other_instructions_length_check
        CHECK (char_length(other_instructions) <= 1500),
    CONSTRAINT ai_coach_custom_instructions_combined_length_check
        CHECK (
            char_length(coaching_priorities)
            + char_length(safety_progression_rules)
            + char_length(training_approach)
            + char_length(recovery_adjustment_rules)
            + char_length(communication_style)
            + char_length(planning_preferences)
            + char_length(other_instructions) <= 8000
        )
);

COMMENT ON TABLE public.ai_coach_custom_instructions IS
    'Singleton durable Custom Instructions profile for AI Coach. These stable preferences do not replace product policy, authoritative Training Intelligence, or Durable Memories.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.instructions_id IS
    'Singleton identifier. The only supported value is 1.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.coaching_priorities IS
    'Stable priorities that determine what wins when coaching goals conflict, such as safety, consistency, availability, enjoyment, strength, and sustainable performance.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.safety_progression_rules IS
    'Stable safety thresholds and overrides, such as ramp review, poor-sleep adjustments, travel recovery, and clinician or injury overrides.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.training_approach IS
    'Durable training model and preferences, including volume, strength, intentional intensity, technical demands, and avoidance of generic advice.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.recovery_adjustment_rules IS
    'Stable recommendation adjustments for sleep, soreness, illness, travel, missing subjective context, weight changes, and reduced training.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.communication_style IS
    'Preferred response tone and format, including concise summaries, actionable bullets, direct language, meaningful risk sections, explicit dates, and concise-format requests.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.planning_preferences IS
    'Practical planning preferences, including time estimates, strength preservation, life stress, modified alternatives, fueling cues, enjoyment, and sustainable progression.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.other_instructions IS
    'Optional bounded instructions that do not fit the six main sections. This is not a memory dump, weekly plan, temporary injury note, or unlimited second prompt.';
COMMENT ON COLUMN public.ai_coach_custom_instructions.updated_at IS
    'Timestamp of the most recent profile update. Future application updates should set this explicitly with now().';

-- Seed the blank singleton without overwriting any later reviewed content.
INSERT INTO public.ai_coach_custom_instructions (
    instructions_id,
    coaching_priorities,
    safety_progression_rules,
    training_approach,
    recovery_adjustment_rules,
    communication_style,
    planning_preferences,
    other_instructions
)
VALUES (1, '', '', '', '', '', '', '')
ON CONFLICT (instructions_id) DO NOTHING;

-- Read-only verification queries for manual review after execution.
SELECT
    count(*) AS singleton_row_count,
    count(*) = 1 AS exactly_one_singleton_row,
    bool_and(instructions_id = 1) AS singleton_id_is_valid,
    max(updated_at) IS NOT NULL AS updated_at_is_populated
FROM public.ai_coach_custom_instructions;

SELECT
    instructions_id,
    char_length(coaching_priorities) <= 1500
        AND char_length(safety_progression_rules) <= 1500
        AND char_length(training_approach) <= 1500
        AND char_length(recovery_adjustment_rules) <= 1500
        AND char_length(communication_style) <= 1500
        AND char_length(planning_preferences) <= 1500
        AND char_length(other_instructions) <= 1500 AS section_limits_are_valid,
    char_length(coaching_priorities)
        + char_length(safety_progression_rules)
        + char_length(training_approach)
        + char_length(recovery_adjustment_rules)
        + char_length(communication_style)
        + char_length(planning_preferences)
        + char_length(other_instructions) AS combined_character_count,
    char_length(coaching_priorities)
        + char_length(safety_progression_rules)
        + char_length(training_approach)
        + char_length(recovery_adjustment_rules)
        + char_length(communication_style)
        + char_length(planning_preferences)
        + char_length(other_instructions) <= 8000 AS combined_limit_is_valid,
    updated_at IS NOT NULL AS updated_at_is_populated
FROM public.ai_coach_custom_instructions
WHERE instructions_id = 1;
