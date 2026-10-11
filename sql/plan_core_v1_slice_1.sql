-- Plan Core V1 Slice 1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.

BEGIN;

CREATE TABLE public.plan_category (
    plan_category_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    category_key text NOT NULL,
    category_name text NOT NULL,
    color_key text NULL,
    icon_key text NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT plan_category_pkey PRIMARY KEY (plan_category_id),
    CONSTRAINT plan_category_category_key_key UNIQUE (category_key),
    CONSTRAINT plan_category_category_key_check CHECK (btrim(category_key) <> ''),
    CONSTRAINT plan_category_category_name_check CHECK (btrim(category_name) <> ''),
    CONSTRAINT plan_category_sort_order_check CHECK (sort_order >= 0)
);

CREATE INDEX plan_category_active_order_idx
    ON public.plan_category USING btree (sort_order, category_name)
    WHERE is_active;

CREATE TABLE public.plan_prescription (
    plan_prescription_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    owner_kind text NOT NULL,
    title text NOT NULL,
    description text NULL,
    sport_type text NULL,
    activity_category text NULL,
    trainer boolean NULL,
    target_duration_min numeric(7, 2) NULL,
    target_load integer NULL,
    target_load_source text NULL,
    target_distance_mi numeric(10, 3) NULL,
    target_elevation_ft integer NULL,
    instruction_text text NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT plan_prescription_pkey PRIMARY KEY (plan_prescription_id),
    CONSTRAINT plan_prescription_id_owner_kind_key UNIQUE (plan_prescription_id, owner_kind),
    CONSTRAINT plan_prescription_owner_kind_check CHECK (owner_kind IN ('template', 'item')),
    CONSTRAINT plan_prescription_title_check CHECK (btrim(title) <> ''),
    CONSTRAINT plan_prescription_sport_type_check
        CHECK (sport_type IS NULL OR btrim(sport_type) <> ''),
    CONSTRAINT plan_prescription_activity_category_check
        CHECK (activity_category IS NULL OR btrim(activity_category) <> ''),
    CONSTRAINT plan_prescription_target_load_source_check
        CHECK (target_load_source IS NULL OR btrim(target_load_source) <> ''),
    CONSTRAINT plan_prescription_target_duration_check
        CHECK (target_duration_min IS NULL OR target_duration_min >= 0),
    CONSTRAINT plan_prescription_target_load_check
        CHECK (target_load IS NULL OR target_load >= 0),
    CONSTRAINT plan_prescription_target_distance_check
        CHECK (target_distance_mi IS NULL OR target_distance_mi >= 0),
    CONSTRAINT plan_prescription_target_elevation_check
        CHECK (target_elevation_ft IS NULL OR target_elevation_ft >= 0)
);

CREATE TABLE public.plan_prescription_segment (
    plan_prescription_segment_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    plan_prescription_id bigint NOT NULL,
    segment_order smallint NOT NULL,
    segment_name text NULL,
    repeat_group_key smallint NULL,
    repeat_count smallint DEFAULT 1 NOT NULL,
    target_duration_min numeric(7, 2) NULL,
    target_metric text DEFAULT 'none' NOT NULL,
    zone_min smallint NULL,
    zone_max smallint NULL,
    target_value_min numeric(8, 2) NULL,
    target_value_max numeric(8, 2) NULL,
    instruction_text text NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT plan_prescription_segment_pkey PRIMARY KEY (plan_prescription_segment_id),
    CONSTRAINT plan_prescription_segment_prescription_order_key
        UNIQUE (plan_prescription_id, segment_order),
    CONSTRAINT plan_prescription_segment_prescription_fkey
        FOREIGN KEY (plan_prescription_id)
        REFERENCES public.plan_prescription(plan_prescription_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT plan_prescription_segment_order_check CHECK (segment_order > 0),
    CONSTRAINT plan_prescription_segment_repeat_count_check CHECK (repeat_count > 0),
    CONSTRAINT plan_prescription_segment_repeat_group_key_check
        CHECK (repeat_group_key IS NULL OR repeat_group_key > 0),
    CONSTRAINT plan_prescription_segment_repeat_group_check
        CHECK (repeat_group_key IS NOT NULL OR repeat_count = 1),
    CONSTRAINT plan_prescription_segment_target_duration_check
        CHECK (target_duration_min IS NULL OR target_duration_min >= 0),
    CONSTRAINT plan_prescription_segment_zone_bounds_check
        CHECK (
            (zone_min IS NULL AND zone_max IS NULL)
            OR (
                zone_min IS NOT NULL
                AND zone_max IS NOT NULL
                AND zone_min > 0
                AND zone_max > 0
                AND zone_min <= zone_max
            )
        ),
    CONSTRAINT plan_prescription_segment_target_values_check
        CHECK (
            (target_value_min IS NULL AND target_value_max IS NULL)
            OR (
                target_value_min IS NOT NULL
                AND target_value_max IS NOT NULL
                AND target_value_min >= 0
                AND target_value_max >= 0
                AND target_value_min <= target_value_max
            )
        ),
    CONSTRAINT plan_prescription_segment_target_exclusive_check
        CHECK (zone_min IS NULL OR target_value_min IS NULL),
    CONSTRAINT plan_prescription_segment_target_metric_check
        CHECK (btrim(target_metric) <> ''),
    CONSTRAINT plan_prescription_segment_target_consistency_check
        CHECK (
            (
                target_metric = 'none'
                AND zone_min IS NULL
                AND zone_max IS NULL
                AND target_value_min IS NULL
                AND target_value_max IS NULL
            )
            OR (
                target_metric <> 'none'
                AND (
                    (
                        zone_min IS NOT NULL
                        AND zone_max IS NOT NULL
                        AND target_value_min IS NULL
                        AND target_value_max IS NULL
                    )
                    OR (
                        zone_min IS NULL
                        AND zone_max IS NULL
                        AND target_value_min IS NOT NULL
                        AND target_value_max IS NOT NULL
                    )
                )
            )
        ),
    CONSTRAINT plan_prescription_segment_content_check
        CHECK (
            btrim(coalesce(segment_name, '')) <> ''
            OR btrim(coalesce(instruction_text, '')) <> ''
            OR target_duration_min IS NOT NULL
            OR zone_min IS NOT NULL
            OR target_value_min IS NOT NULL
        )
);

CREATE TABLE public.plan_template (
    plan_template_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    plan_category_id bigint NOT NULL,
    plan_prescription_id bigint NOT NULL,
    prescription_owner_kind text DEFAULT 'template' NOT NULL,
    template_name text NOT NULL,
    template_description text NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT plan_template_pkey PRIMARY KEY (plan_template_id),
    CONSTRAINT plan_template_prescription_id_key UNIQUE (plan_prescription_id),
    CONSTRAINT plan_template_category_fkey
        FOREIGN KEY (plan_category_id)
        REFERENCES public.plan_category(plan_category_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT plan_template_prescription_owner_fkey
        FOREIGN KEY (plan_prescription_id, prescription_owner_kind)
        REFERENCES public.plan_prescription(plan_prescription_id, owner_kind)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT plan_template_prescription_owner_kind_check
        CHECK (prescription_owner_kind = 'template'),
    CONSTRAINT plan_template_name_check CHECK (btrim(template_name) <> ''),
    CONSTRAINT plan_template_sort_order_check CHECK (sort_order >= 0)
);

CREATE INDEX plan_template_category_order_idx
    ON public.plan_template USING btree (plan_category_id, sort_order, template_name)
    WHERE is_active;

CREATE TABLE public.plan_batch (
    plan_batch_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    batch_type text NOT NULL,
    batch_status text DEFAULT 'open' NOT NULL,
    batch_name text NULL,
    range_start date NULL,
    range_end date NULL,
    source_reference text NULL,
    idempotency_key text NULL,
    created_by text DEFAULT 'user' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    committed_at timestamptz NULL,
    discarded_at timestamptz NULL,
    CONSTRAINT plan_batch_pkey PRIMARY KEY (plan_batch_id),
    CONSTRAINT plan_batch_type_check CHECK (btrim(batch_type) <> ''),
    CONSTRAINT plan_batch_status_check
        CHECK (batch_status IN ('open', 'committed', 'discarded')),
    CONSTRAINT plan_batch_idempotency_key_check
        CHECK (idempotency_key IS NULL OR btrim(idempotency_key) <> ''),
    CONSTRAINT plan_batch_created_by_check CHECK (btrim(created_by) <> ''),
    CONSTRAINT plan_batch_range_check
        CHECK (
            (range_start IS NULL AND range_end IS NULL)
            OR (
                range_start IS NOT NULL
                AND range_end IS NOT NULL
                AND range_end >= range_start
            )
        ),
    CONSTRAINT plan_batch_terminal_times_check
        CHECK (
            (batch_status = 'open' AND committed_at IS NULL AND discarded_at IS NULL)
            OR (
                batch_status = 'committed'
                AND committed_at IS NOT NULL
                AND discarded_at IS NULL
            )
            OR (
                batch_status = 'discarded'
                AND discarded_at IS NOT NULL
                AND committed_at IS NULL
            )
        ),
    CONSTRAINT plan_batch_time_order_check
        CHECK (
            (committed_at IS NULL OR committed_at >= created_at)
            AND (discarded_at IS NULL OR discarded_at >= created_at)
        ),
    CONSTRAINT plan_batch_updated_at_check CHECK (updated_at >= created_at)
);

CREATE UNIQUE INDEX plan_batch_idempotency_key_uidx
    ON public.plan_batch USING btree (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX plan_batch_open_updated_idx
    ON public.plan_batch USING btree (updated_at DESC, plan_batch_id DESC)
    WHERE batch_status = 'open';

CREATE TABLE public.plan_item (
    plan_item_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    plan_batch_id bigint NULL,
    source_template_id bigint NULL,
    plan_category_id bigint NOT NULL,
    plan_prescription_id bigint NOT NULL,
    prescription_owner_kind text DEFAULT 'item' NOT NULL,
    planned_date date NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    item_state text NOT NULL,
    item_source text DEFAULT 'manual' NOT NULL,
    user_note text NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    committed_at timestamptz NULL,
    cancelled_at timestamptz NULL,
    CONSTRAINT plan_item_pkey PRIMARY KEY (plan_item_id),
    CONSTRAINT plan_item_prescription_id_key UNIQUE (plan_prescription_id),
    CONSTRAINT plan_item_source_check CHECK (btrim(item_source) <> ''),
    CONSTRAINT plan_item_batch_fkey
        FOREIGN KEY (plan_batch_id)
        REFERENCES public.plan_batch(plan_batch_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT plan_item_source_template_fkey
        FOREIGN KEY (source_template_id)
        REFERENCES public.plan_template(plan_template_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT plan_item_category_fkey
        FOREIGN KEY (plan_category_id)
        REFERENCES public.plan_category(plan_category_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT plan_item_prescription_owner_fkey
        FOREIGN KEY (plan_prescription_id, prescription_owner_kind)
        REFERENCES public.plan_prescription(plan_prescription_id, owner_kind)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT plan_item_prescription_owner_kind_check
        CHECK (prescription_owner_kind = 'item'),
    CONSTRAINT plan_item_state_check
        CHECK (item_state IN ('draft', 'committed', 'cancelled')),
    CONSTRAINT plan_item_lifecycle_times_check
        CHECK (
            (
                item_state = 'draft'
                AND plan_batch_id IS NOT NULL
                AND committed_at IS NULL
                AND cancelled_at IS NULL
            )
            OR (
                item_state = 'committed'
                AND committed_at IS NOT NULL
                AND cancelled_at IS NULL
            )
            OR (item_state = 'cancelled' AND cancelled_at IS NOT NULL)
        ),
    CONSTRAINT plan_item_time_order_check
        CHECK (
            (committed_at IS NULL OR committed_at >= created_at)
            AND (cancelled_at IS NULL OR cancelled_at >= created_at)
            AND (
                committed_at IS NULL
                OR cancelled_at IS NULL
                OR cancelled_at >= committed_at
            )
        ),
    CONSTRAINT plan_item_updated_at_check CHECK (updated_at >= created_at),
    CONSTRAINT plan_item_sort_order_check CHECK (sort_order >= 0)
);

CREATE INDEX plan_item_calendar_idx
    ON public.plan_item USING btree (planned_date, sort_order, plan_item_id)
    WHERE item_state IN ('draft', 'committed');

CREATE INDEX plan_item_batch_idx
    ON public.plan_item USING btree (plan_batch_id, item_state, planned_date, sort_order)
    WHERE plan_batch_id IS NOT NULL;

INSERT INTO public.plan_category (
    category_key,
    category_name,
    sort_order,
    color_key,
    icon_key,
    is_active
)
VALUES
    ('endurance', 'Endurance', 1, NULL, NULL, true),
    ('intensity', 'Intensity', 2, NULL, NULL, true),
    ('strength', 'Strength', 3, NULL, NULL, true),
    ('recovery', 'Recovery', 4, NULL, NULL, true),
    ('rest', 'Rest', 5, NULL, NULL, true),
    ('bike_park', 'Bike Park', 6, NULL, NULL, true),
    ('event', 'Event', 7, NULL, NULL, true),
    ('travel', 'Travel', 8, NULL, NULL, true),
    ('rehabilitation', 'Rehabilitation', 9, NULL, NULL, true)
ON CONFLICT (category_key) DO NOTHING;

COMMIT;

-- Read-only verification queries for manual review after execution.
SELECT table_name, column_name, data_type, is_nullable, column_default, is_identity
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
      'plan_category',
      'plan_prescription',
      'plan_prescription_segment',
      'plan_template',
      'plan_batch',
      'plan_item'
  )
ORDER BY table_name, ordinal_position;

SELECT c.relname AS table_name,
       con.conname AS constraint_name,
       pg_get_constraintdef(con.oid) AS constraint_definition,
       con.confdeltype,
       con.confupdtype
FROM pg_constraint AS con
JOIN pg_class AS c ON c.oid = con.conrelid
WHERE con.connamespace = 'public'::regnamespace
  AND c.relname LIKE 'plan_%'
ORDER BY table_name, constraint_name;

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
      'plan_category',
      'plan_prescription',
      'plan_prescription_segment',
      'plan_template',
      'plan_batch',
      'plan_item'
  )
ORDER BY tablename, indexname;

SELECT category_key, category_name, sort_order, color_key, icon_key, is_active
FROM public.plan_category
ORDER BY sort_order, category_key;

SELECT
    (SELECT count(*) FROM public.plan_prescription) AS prescription_count,
    (SELECT count(*) FROM public.plan_prescription_segment) AS segment_count,
    (SELECT count(*) FROM public.plan_template) AS template_count,
    (SELECT count(*) FROM public.plan_batch) AS batch_count,
    (SELECT count(*) FROM public.plan_item) AS item_count,
    (SELECT count(*) FROM public.plan_category) AS category_count;

SELECT p.plan_prescription_id, p.owner_kind
FROM public.plan_prescription AS p
WHERE NOT EXISTS (
        SELECT 1
        FROM public.plan_template AS t
        WHERE t.plan_prescription_id = p.plan_prescription_id
          AND t.prescription_owner_kind = p.owner_kind
    )
  AND NOT EXISTS (
        SELECT 1
        FROM public.plan_item AS i
        WHERE i.plan_prescription_id = p.plan_prescription_id
          AND i.prescription_owner_kind = p.owner_kind
    );

-- Before production application, record actual/derived table counts and a verified
-- backup recovery point. Compare those counts after application; this migration
-- must not alter actual or derived tables.
--
-- Rollback is permitted only before any Plan content or category edits exist,
-- after verifying that only untouched seed rows remain. Drop in reverse
-- dependency order: plan_item, plan_batch, plan_template,
-- plan_prescription_segment, plan_prescription, plan_category.
-- Once Plan data or category edits exist, preserve them with forward fixes;
-- do not use DROP ... CASCADE or drop populated Plan tables.
