-- Plan Template Quick Picks V1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.

BEGIN;

ALTER TABLE public.plan_template
    ADD COLUMN IF NOT EXISTS is_favorite boolean;

UPDATE public.plan_template
SET is_favorite = false
WHERE is_favorite IS NULL;

ALTER TABLE public.plan_template
    ALTER COLUMN is_favorite SET DEFAULT false,
    ALTER COLUMN is_favorite SET NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.plan_template AS pt
        JOIN public.plan_category AS pc
          ON pc.plan_category_id = pt.plan_category_id
        WHERE pt.is_active = true
          AND (
              (lower(btrim(pt.template_name)) = 'prehab' AND pc.category_key = 'rehabilitation')
              OR (lower(btrim(pt.template_name)) = 'core strength' AND pc.category_key = 'strength')
              OR (lower(btrim(pt.template_name)) = 'recovery ride' AND pc.category_key = 'recovery')
              OR (lower(btrim(pt.template_name)) = 'rest day' AND pc.category_key = 'rest')
              OR (lower(btrim(pt.template_name)) = 'z2 endurance ride' AND pc.category_key = 'endurance')
              OR (lower(btrim(pt.template_name)) = 'dog walk' AND pc.category_key = 'recovery')
          )
        GROUP BY lower(btrim(pt.template_name)), pc.category_key
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'Ambiguous active Plan template name/category match prevents Quick Pick seeding';
    END IF;

    UPDATE public.plan_template AS pt
    SET is_favorite = true,
        updated_at = now()
    FROM public.plan_category AS pc
    WHERE pc.plan_category_id = pt.plan_category_id
      AND pt.is_active = true
      AND (
          (lower(btrim(pt.template_name)) = 'prehab' AND pc.category_key = 'rehabilitation')
          OR (lower(btrim(pt.template_name)) = 'core strength' AND pc.category_key = 'strength')
          OR (lower(btrim(pt.template_name)) = 'recovery ride' AND pc.category_key = 'recovery')
          OR (lower(btrim(pt.template_name)) = 'rest day' AND pc.category_key = 'rest')
          OR (lower(btrim(pt.template_name)) = 'z2 endurance ride' AND pc.category_key = 'endurance')
          OR (lower(btrim(pt.template_name)) = 'dog walk' AND pc.category_key = 'recovery')
      );
END
$$;

COMMIT;
