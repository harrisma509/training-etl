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