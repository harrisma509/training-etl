BEGIN;

ALTER TABLE public.plan_template
    ADD COLUMN environment text,
    ADD COLUMN saved_location_id bigint;

ALTER TABLE public.plan_item
    ADD COLUMN environment text,
    ADD COLUMN saved_location_id bigint;

UPDATE public.plan_template
SET environment = 'not_applicable';

UPDATE public.plan_item
SET environment = 'not_applicable';

ALTER TABLE public.plan_template
    ALTER COLUMN environment SET NOT NULL,
    ADD CONSTRAINT plan_template_environment_check
        CHECK (environment IN ('outdoor', 'indoor', 'either', 'not_applicable')),
    ADD CONSTRAINT plan_template_saved_location_id_fkey
        FOREIGN KEY (saved_location_id)
        REFERENCES public.saved_location (location_id)
        ON DELETE RESTRICT;

ALTER TABLE public.plan_item
    ALTER COLUMN environment SET NOT NULL,
    ADD CONSTRAINT plan_item_environment_check
        CHECK (environment IN ('outdoor', 'indoor', 'either', 'not_applicable')),
    ADD CONSTRAINT plan_item_saved_location_id_fkey
        FOREIGN KEY (saved_location_id)
        REFERENCES public.saved_location (location_id)
        ON DELETE RESTRICT;

CREATE INDEX plan_template_saved_location_id_idx
    ON public.plan_template (saved_location_id)
    WHERE saved_location_id IS NOT NULL;

CREATE INDEX plan_item_saved_location_id_idx
    ON public.plan_item (saved_location_id)
    WHERE saved_location_id IS NOT NULL;

COMMENT ON COLUMN public.plan_template.environment IS
    'Required environment classification for future Plan template use.';
COMMENT ON COLUMN public.plan_template.saved_location_id IS
    'Optional default saved location copied to newly scheduled Plan items.';
COMMENT ON COLUMN public.plan_item.environment IS
    'Required environment snapshot for this scheduled Plan item.';
COMMENT ON COLUMN public.plan_item.saved_location_id IS
    'Optional saved-location snapshot for this scheduled Plan item.';

SELECT environment, count(*) AS template_count
FROM public.plan_template
GROUP BY environment
ORDER BY environment;

SELECT count(*) AS templates_missing_environment
FROM public.plan_template
WHERE environment IS NULL;

SELECT count(*) AS templates_with_invalid_saved_location
FROM public.plan_template pt
LEFT JOIN public.saved_location sl
    ON sl.location_id = pt.saved_location_id
WHERE pt.saved_location_id IS NOT NULL
  AND sl.location_id IS NULL;

SELECT environment, count(*) AS plan_item_count
FROM public.plan_item
GROUP BY environment
ORDER BY environment;

SELECT count(*) AS plan_items_missing_environment
FROM public.plan_item
WHERE environment IS NULL;

SELECT count(*) AS plan_items_with_invalid_saved_location
FROM public.plan_item pi
LEFT JOIN public.saved_location sl
    ON sl.location_id = pi.saved_location_id
WHERE pi.saved_location_id IS NOT NULL
  AND sl.location_id IS NULL;

COMMIT;
