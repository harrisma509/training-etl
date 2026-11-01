-- Saved Locations persistence contract v1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- No location is seeded; Home coordinates must be supplied through an approved workflow.

BEGIN;

CREATE TABLE public.saved_location (
    location_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
    display_name text NOT NULL,
    latitude numeric(9, 6) NOT NULL,
    longitude numeric(10, 6) NOT NULL,
    timezone_name text NOT NULL,
    location_type text NOT NULL,
    lifecycle_state text DEFAULT 'active' NOT NULL,
    is_home boolean DEFAULT false NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT saved_location_pkey PRIMARY KEY (location_id),
    CONSTRAINT saved_location_display_name_check
        CHECK (btrim(display_name) <> ''),
    CONSTRAINT saved_location_latitude_check
        CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT saved_location_longitude_check
        CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT saved_location_timezone_name_check
        CHECK (btrim(timezone_name) <> ''),
    CONSTRAINT saved_location_location_type_check
        CHECK (location_type IN ('home', 'work', 'training', 'other')),
    CONSTRAINT saved_location_lifecycle_state_check
        CHECK (lifecycle_state IN ('active', 'hidden', 'archived')),
    CONSTRAINT saved_location_home_type_check
        CHECK ((location_type = 'home') = is_home),
    CONSTRAINT saved_location_home_active_check
        CHECK (NOT is_home OR lifecycle_state = 'active'),
    CONSTRAINT saved_location_updated_at_check
        CHECK (updated_at >= created_at)
);

CREATE UNIQUE INDEX saved_location_single_home_idx
    ON public.saved_location (is_home)
    WHERE is_home;

COMMENT ON TABLE public.saved_location IS
    'Durable saved locations. Coordinates remain server-side; this table contains no forecast or provider state.';
COMMENT ON COLUMN public.saved_location.location_id IS
    'Stable identity retained across display-name and lifecycle changes.';
COMMENT ON COLUMN public.saved_location.display_name IS
    'Friendly display name for this saved location.';
COMMENT ON COLUMN public.saved_location.latitude IS
    'Latitude in decimal degrees, stored to six fractional digits.';
COMMENT ON COLUMN public.saved_location.longitude IS
    'Longitude in decimal degrees, stored to six fractional digits.';
COMMENT ON COLUMN public.saved_location.timezone_name IS
    'IANA timezone name used for this location.';
COMMENT ON COLUMN public.saved_location.location_type IS
    'Location category: home, work, training, or other.';
COMMENT ON COLUMN public.saved_location.lifecycle_state IS
    'Location lifecycle: active, hidden, or archived.';
COMMENT ON COLUMN public.saved_location.is_home IS
    'True only for the unique active Home/default location.';
COMMENT ON COLUMN public.saved_location.created_at IS
    'Timestamp when this saved location was created.';
COMMENT ON COLUMN public.saved_location.updated_at IS
    'Timestamp of the most recent saved-location update.';

COMMIT;

-- Read-only verification queries. No coordinates or location names are returned.
SELECT to_regclass('public.saved_location') IS NOT NULL AS saved_location_table_exists;

SELECT
    count(*) FILTER (WHERE is_home) AS home_location_count,
    count(*) AS seeded_location_count
FROM public.saved_location;

SELECT
    conname,
    convalidated
FROM pg_constraint
WHERE conrelid = 'public.saved_location'::regclass
ORDER BY conname;

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'saved_location'
  AND indexname = 'saved_location_single_home_idx';

-- Rollback consideration: dropping this table destroys saved-location data.
-- Do not drop it after locations have been created or referenced.
