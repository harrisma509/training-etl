-- Generic application preference storage V1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.

BEGIN;

CREATE TABLE public.app_preference (
    preference_namespace text NOT NULL,
    preference_value jsonb NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT app_preference_pkey PRIMARY KEY (preference_namespace),
    CONSTRAINT app_preference_namespace_check
        CHECK (btrim(preference_namespace) <> ''),
    CONSTRAINT app_preference_value_object_check
        CHECK (jsonb_typeof(preference_value) = 'object')
);

COMMENT ON TABLE public.app_preference IS
    'Generic single-user application preferences, separated by validated namespace. Browser requests must use strict namespace-specific contracts.';
COMMENT ON COLUMN public.app_preference.preference_namespace IS
    'Unique nonblank owner namespace for one application preference record.';
COMMENT ON COLUMN public.app_preference.preference_value IS
    'Validated namespace-specific preference object. Applications must strictly allowlist browser-controlled keys and types.';
COMMENT ON COLUMN public.app_preference.updated_at IS
    'Timestamp of the most recent preference update.';

INSERT INTO public.app_preference (preference_namespace, preference_value)
VALUES ('plan_view', '{"hide_past_planned": true}'::jsonb)
ON CONFLICT (preference_namespace) DO NOTHING;

COMMIT;

-- Read-only verification queries for manual review after execution.
SELECT preference_namespace, preference_value, updated_at
FROM public.app_preference
WHERE preference_namespace = 'plan_view';

SELECT c.relname AS table_name,
       con.conname AS constraint_name,
       pg_get_constraintdef(con.oid) AS constraint_definition
FROM pg_constraint AS con
JOIN pg_class AS c ON c.oid = con.conrelid
WHERE c.relname = 'app_preference'
ORDER BY con.conname;

-- Rollback (destructive for preference values stored after this migration):
-- BEGIN;
-- DROP TABLE public.app_preference;
-- COMMIT;
