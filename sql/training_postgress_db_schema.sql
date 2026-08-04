-- public.daily_training definition

-- Drop table

-- DROP TABLE public.daily_training;

CREATE TABLE public.daily_training (
	"date" date NOT NULL,
	activity_count int4 NULL,
	activity_categories text NULL,
	ride_count int4 NULL,
	walk_count int4 NULL,
	hike_count int4 NULL,
	strength_count int4 NULL,
	mobility_count int4 NULL,
	ski_count int4 NULL,
	run_count int4 NULL,
	other_count int4 NULL,
	main_ride_id text NULL,
	main_ride_name text NULL,
	main_ride_sport_type text NULL,
	main_ride_category text NULL,
	main_ride_time text NULL,
	main_ride_elapsed_time text NULL,
	main_ride_miles numeric NULL,
	main_ride_elevation_ft int4 NULL,
	main_ride_gear_id text NULL,
	main_ride_bike_name text NULL,
	main_ride_rpe int4 NULL,
	main_ride_load_source text NULL,
	main_ride_load int4 NULL,
	main_ride_load_score numeric NULL,
	main_ride_band text NULL,
	main_ride_load_text text NULL,
	main_ride_hr_zones text NULL,
	z1_sec int4 NULL,
	z2_sec int4 NULL,
	z3_sec int4 NULL,
	z4_sec int4 NULL,
	z5_sec int4 NULL,
	z4_z5_sec int4 NULL,
	stream_moving_sec int4 NULL,
	other_activity_count int4 NULL,
	other_activity_names text NULL,
	other_time text NULL,
	other_miles numeric NULL,
	other_elevation_ft int4 NULL,
	other_load int4 NULL,
	other_load_raw numeric NULL,
	total_load int4 NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT daily_training_pkey PRIMARY KEY (date)
);


-- public.gear definition

-- Drop table

-- DROP TABLE public.gear;

CREATE TABLE public.gear (
	gear_id text NOT NULL,
	gear_name text NOT NULL,
	gear_type text NOT NULL,
	retired bool DEFAULT false NULL,
	brand text NULL,
	model_year int4 NULL,
	acquisition_date date NULL,
	retirement_date date NULL,
	notes text NULL,
	active bool DEFAULT true NULL,
	created_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	updated_at timestamp DEFAULT CURRENT_TIMESTAMP NULL,
	category text NULL,
	CONSTRAINT gear_pkey PRIMARY KEY (gear_id)
);


-- public.sync_request definition

-- Drop table

-- DROP TABLE public.sync_request;

CREATE TABLE public.sync_request (
	id bigserial NOT NULL,
	requested_at_utc timestamptz DEFAULT now() NOT NULL,
	requested_by text DEFAULT 'dashboard'::text NOT NULL,
	days_back int4 DEFAULT 1 NOT NULL,
	status text DEFAULT 'pending'::text NOT NULL,
	started_at_utc timestamptz NULL,
	completed_at_utc timestamptz NULL,
	message text NULL,
	CONSTRAINT sync_request_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_sync_request_status_requested ON public.sync_request USING btree (status, requested_at_utc);


-- public.sync_run_log definition

-- Drop table

-- DROP TABLE public.sync_run_log;

CREATE TABLE public.sync_run_log (
	id bigserial NOT NULL,
	run_at_utc timestamptz NOT NULL,
	days_back int4 NULL,
	activity_count int4 NULL,
	daily_rows int4 NULL,
	weekly_rows int4 NULL,
	warning_count int4 NULL,
	status text NULL,
	created_at timestamptz DEFAULT now() NULL,
	CONSTRAINT sync_run_log_pkey PRIMARY KEY (id)
);


-- public.weekly_training definition

-- Drop table

-- DROP TABLE public.weekly_training;

CREATE TABLE public.weekly_training (
	week_start date NOT NULL,
	week_end date NULL,
	total_load int4 NULL,
	main_ride_load int4 NULL,
	other_load int4 NULL,
	activity_days int4 NULL,
	ride_count int4 NULL,
	walk_count int4 NULL,
	hike_count int4 NULL,
	strength_count int4 NULL,
	mobility_count int4 NULL,
	ski_count int4 NULL,
	run_count int4 NULL,
	other_count int4 NULL,
	very_hard_epic_days int4 NULL,
	chronic_daily_c numeric NULL,
	chronic_weekly_cw numeric NULL,
	ac_ratio numeric NULL,
	ramp_pct numeric NULL,
	ramp_pct_display text NULL,
	remaining_to_20pct_ramp int4 NULL,
	status_level text NULL,
	status_text text NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT weekly_training_pkey PRIMARY KEY (week_start)
);

CREATE TABLE IF NOT EXISTS weekly_audit (
    week_start DATE PRIMARY KEY,
    audit_version TEXT NOT NULL DEFAULT 'v1',
    overall_grade TEXT,
    green_count INTEGER NOT NULL DEFAULT 0,
    yellow_count INTEGER NOT NULL DEFAULT 0,
    red_count INTEGER NOT NULL DEFAULT 0,
    audit_summary TEXT,
    next_week_action TEXT,
    source TEXT NOT NULL DEFAULT 'computed',
    computed_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_overall_grade
ON weekly_audit (overall_grade);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_source
ON weekly_audit (source);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_computed_at
ON weekly_audit (computed_at);

CREATE TABLE IF NOT EXISTS weekly_audit_item (
    id BIGSERIAL PRIMARY KEY,
    week_start DATE NOT NULL,
    item_key TEXT NOT NULL,
    item_label TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    sort_order INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'computed',
    evidence_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_weekly_audit_item_week_key
        UNIQUE (week_start, item_key)
);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_week_start
ON weekly_audit_item (week_start);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_status
ON weekly_audit_item (status);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_key
ON weekly_audit_item (item_key);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_evidence_json
ON weekly_audit_item
USING GIN (evidence_json);


-- public.strava_activities definition

-- Drop table

-- DROP TABLE public.strava_activities;

CREATE TABLE public.strava_activities (
	activity_id text NOT NULL,
	date_local date NOT NULL,
	"name" text NULL,
	sport_type text NULL,
	activity_category text NULL,
	moving_sec int4 NULL,
	elapsed_sec int4 NULL,
	distance_mi numeric NULL,
	elevation_ft int4 NULL,
	has_heartrate bool NULL,
	average_hr numeric NULL,
	max_hr numeric NULL,
	gear_id text NULL,
	bike_name text NULL,
	raw_json jsonb NULL,
	updated_at timestamptz DEFAULT now() NULL,
	CONSTRAINT strava_activities_pkey PRIMARY KEY (activity_id),
	CONSTRAINT fk_strava_activities_gear FOREIGN KEY (gear_id) REFERENCES public.gear(gear_id)
);
CREATE INDEX idx_strava_activities_gear_id ON public.strava_activities USING btree (gear_id);

CREATE TABLE IF NOT EXISTS health_weight (
    date DATE PRIMARY KEY,
    measured_at TIMESTAMPTZ,
    weight_lb NUMERIC,
    body_fat_pct NUMERIC,
    lean_body_mass_lb NUMERIC,
    bmi NUMERIC,
    source TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS health_rhr (
	date DATE PRIMARY KEY,
	measured_at TIMESTAMPTZ NOT NULL,
	rhr_bpm INTEGER NOT NULL CHECK (rhr_bpm > 0),
	source TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_health_rhr_measured_at
ON health_rhr (measured_at);

CREATE TABLE IF NOT EXISTS health_steps (
	date DATE PRIMARY KEY,
	measured_at TIMESTAMPTZ NOT NULL,
	steps INTEGER NOT NULL CHECK (steps >= 0),
	source TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_health_steps_measured_at
ON health_steps (measured_at);

CREATE TABLE IF NOT EXISTS health_hrv (
	date DATE PRIMARY KEY,
	measured_at TIMESTAMPTZ NOT NULL,
	hrv_sdnn_ms NUMERIC NOT NULL CHECK (hrv_sdnn_ms > 0),
	source TEXT,
	sample_timestamp TIMESTAMPTZ,
	mins_before_wake INTEGER,
	rule TEXT,
	proximity_level TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_hrv_measured_at
ON health_hrv (measured_at);

CREATE INDEX IF NOT EXISTS idx_health_hrv_sample_timestamp
ON health_hrv (sample_timestamp);

CREATE TABLE IF NOT EXISTS health_sleep (
	date DATE PRIMARY KEY,
	sleep_start TIMESTAMPTZ,
	sleep_end TIMESTAMPTZ,
	in_bed_start TIMESTAMPTZ,
	in_bed_end TIMESTAMPTZ,
	deep_sleep_hr NUMERIC,
	core_sleep_hr NUMERIC,
	rem_sleep_hr NUMERIC,
	awake_hr NUMERIC,
	total_sleep_hr NUMERIC,
	asleep_hr NUMERIC,
	in_bed_hr NUMERIC,
	sleep_score INTEGER,
	duration_pts INTEGER,
	consistency_pts INTEGER,
	interruptions_pts INTEGER,
	score_version TEXT,
	source TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS health_vo2_max (
	week_start DATE PRIMARY KEY,
	measured_at TIMESTAMPTZ NOT NULL,
	vo2max NUMERIC NOT NULL CHECK (vo2max > 0),
	source TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_health_vo2_max_measured_at
ON health_vo2_max (measured_at);

CREATE TABLE IF NOT EXISTS health_falls (
	date DATE PRIMARY KEY,
	measured_at TIMESTAMPTZ NOT NULL,
	falls INTEGER NOT NULL CHECK (falls >= 0),
	source TEXT,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_health_falls_measured_at
ON health_falls (measured_at);

CREATE OR REPLACE VIEW public.weekly_zone_summary AS
WITH daily_zone_source AS (
	SELECT
		(
			"date"
			- ((EXTRACT(ISODOW FROM "date")::int - 1) * INTERVAL '1 day')
		)::date AS week_start,

		COALESCE(ride_count, 0) AS ride_count,
		COALESCE(z1_sec, 0) AS z1_sec,
		COALESCE(z2_sec, 0) AS z2_sec,
		COALESCE(z3_sec, 0) AS z3_sec,
		COALESCE(z4_sec, 0) AS z4_sec,
		COALESCE(z5_sec, 0) AS z5_sec,
		COALESCE(stream_moving_sec, 0) AS stream_moving_sec
	FROM public.daily_training
),
weekly AS (
	SELECT
		week_start,
		week_start + 6 AS week_end,

		SUM(ride_count)::int AS ride_count,

		SUM(z1_sec)::bigint AS z1_sec,
		SUM(z2_sec)::bigint AS z2_sec,
		SUM(z3_sec)::bigint AS z3_sec,
		SUM(z4_sec)::bigint AS z4_sec,
		SUM(z5_sec)::bigint AS z5_sec,
		SUM(stream_moving_sec)::bigint AS stream_moving_sec
	FROM daily_zone_source
	GROUP BY week_start
),
calc AS (
	SELECT
		week_start,
		week_end,
		ride_count,

		z1_sec,
		z2_sec,
		z3_sec,
		z4_sec,
		z5_sec,
		stream_moving_sec,

		z1_sec + z2_sec AS z1_z2_sec,
		z4_sec + z5_sec AS z4_z5_sec,
		z1_sec + z2_sec + z3_sec + z4_sec + z5_sec AS zone_total_sec
	FROM weekly
)
SELECT
	week_start,
	week_end,
	ride_count,

	zone_total_sec AS ride_time_sec,
	z1_z2_sec,
	z3_sec,
	z4_z5_sec,
	z1_sec,
	z2_sec,
	z4_sec,
	z5_sec,
	stream_moving_sec,

	stream_moving_sec - zone_total_sec AS zone_time_delta_sec,

	CASE
		WHEN zone_total_sec > 0 THEN ROUND((z1_z2_sec::numeric / zone_total_sec) * 100, 0)::int
		ELSE NULL
	END AS z1_z2_pct,

	CASE
		WHEN zone_total_sec > 0 THEN ROUND((z3_sec::numeric / zone_total_sec) * 100, 0)::int
		ELSE NULL
	END AS z3_pct,

	CASE
		WHEN zone_total_sec > 0 THEN ROUND((z4_z5_sec::numeric / zone_total_sec) * 100, 0)::int
		ELSE NULL
	END AS z4_z5_pct,

	CASE
		WHEN stream_moving_sec > 0 THEN ROUND((zone_total_sec::numeric / stream_moving_sec) * 100, 0)::int
		ELSE NULL
	END AS zone_coverage_pct,

	(zone_total_sec / 3600)::text || ':' ||
		LPAD(((zone_total_sec % 3600) / 60)::text, 2, '0') AS ride_time_hhmm,

	(z1_z2_sec / 3600)::text || ':' ||
		LPAD(((z1_z2_sec % 3600) / 60)::text, 2, '0') AS z1_z2_hhmm,

	(z3_sec / 3600)::text || ':' ||
		LPAD(((z3_sec % 3600) / 60)::text, 2, '0') AS z3_hhmm,

	(z4_z5_sec / 3600)::text || ':' ||
		LPAD(((z4_z5_sec % 3600) / 60)::text, 2, '0') AS z4_z5_hhmm,

	(z1_sec / 3600)::text || ':' ||
		LPAD(((z1_sec % 3600) / 60)::text, 2, '0') AS z1_hhmm,

	(z2_sec / 3600)::text || ':' ||
		LPAD(((z2_sec % 3600) / 60)::text, 2, '0') AS z2_hhmm,

	(z4_sec / 3600)::text || ':' ||
		LPAD(((z4_sec % 3600) / 60)::text, 2, '0') AS z4_hhmm,

	(z5_sec / 3600)::text || ':' ||
		LPAD(((z5_sec % 3600) / 60)::text, 2, '0') AS z5_hhmm,

	CASE
		WHEN zone_total_sec = 0 THEN 'No zone data'
		WHEN ROUND((z4_z5_sec::numeric / zone_total_sec) * 100, 0)::int > 20 THEN 'High intensity-heavy'
		WHEN ROUND((z3_sec::numeric / zone_total_sec) * 100, 0)::int > 30 THEN 'Tempo-heavy'
		WHEN ROUND((z1_z2_sec::numeric / zone_total_sec) * 100, 0)::int < 60 THEN 'Low aerobic share'
		WHEN ROUND((z1_z2_sec::numeric / zone_total_sec) * 100, 0)::int BETWEEN 60 AND 80
			 AND ROUND((z3_sec::numeric / zone_total_sec) * 100, 0)::int BETWEEN 10 AND 30
			 AND ROUND((z4_z5_sec::numeric / zone_total_sec) * 100, 0)::int <= 10 THEN 'Target distribution'
		WHEN ROUND((z1_z2_sec::numeric / zone_total_sec) * 100, 0)::int > 80
			 AND ROUND((z4_z5_sec::numeric / zone_total_sec) * 100, 0)::int <= 10 THEN 'Easy-heavy'
		ELSE 'Review'
	END AS zone_flag
FROM calc
WHERE zone_total_sec > 0;

CREATE TABLE IF NOT EXISTS weekly_audit_item (
    id BIGSERIAL PRIMARY KEY,

    week_start DATE NOT NULL,

    item_key TEXT NOT NULL,
    item_label TEXT NOT NULL,

    status TEXT NOT NULL,
    summary TEXT,

    sort_order INTEGER NOT NULL,

    source TEXT NOT NULL DEFAULT 'computed',

    evidence_json JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_weekly_audit_item_week_key
        UNIQUE (week_start, item_key)
);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_week_start
ON weekly_audit_item (week_start);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_status
ON weekly_audit_item (status);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_key
ON weekly_audit_item (item_key);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_item_evidence_json
ON weekly_audit_item
USING GIN (evidence_json);

CREATE TABLE IF NOT EXISTS weekly_audit (
    week_start DATE PRIMARY KEY,

    audit_version TEXT NOT NULL DEFAULT 'v1',

    overall_grade TEXT,
    green_count INTEGER NOT NULL DEFAULT 0,
    yellow_count INTEGER NOT NULL DEFAULT 0,
    red_count INTEGER NOT NULL DEFAULT 0,

    audit_summary TEXT,
    next_week_action TEXT,

    source TEXT NOT NULL DEFAULT 'computed',

    computed_at TIMESTAMPTZ,
    reviewed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_overall_grade
ON weekly_audit (overall_grade);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_source
ON weekly_audit (source);

CREATE INDEX IF NOT EXISTS idx_weekly_audit_computed_at
ON weekly_audit (computed_at);