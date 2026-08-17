-- DROP SCHEMA public;

CREATE SCHEMA public AUTHORIZATION pg_database_owner;

COMMENT ON SCHEMA public IS 'standard public schema';

-- DROP SEQUENCE public.gear_component_gear_component_id_seq;

CREATE SEQUENCE public.gear_component_gear_component_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.service_event_service_event_id_seq;

CREATE SEQUENCE public.service_event_service_event_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.sync_request_id_seq;

CREATE SEQUENCE public.sync_request_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.sync_run_log_id_seq;

CREATE SEQUENCE public.sync_run_log_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.training_year_run_training_year_run_id_seq;

CREATE SEQUENCE public.training_year_run_training_year_run_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.weekly_audit_item_id_seq;

CREATE SEQUENCE public.weekly_audit_item_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;-- public.daily_training definition

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


-- public.health_falls definition

-- Drop table

-- DROP TABLE public.health_falls;

CREATE TABLE public.health_falls (
	"date" date NOT NULL,
	measured_at timestamptz NOT NULL,
	falls int4 NOT NULL,
	"source" text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_falls_falls_check CHECK ((falls >= 0)),
	CONSTRAINT health_falls_pkey PRIMARY KEY (date)
);
CREATE INDEX idx_health_falls_measured_at ON public.health_falls USING btree (measured_at);


-- public.health_hrv definition

-- Drop table

-- DROP TABLE public.health_hrv;

CREATE TABLE public.health_hrv (
	"date" date NOT NULL,
	measured_at timestamptz NOT NULL,
	hrv_sdnn_ms numeric NOT NULL,
	"source" text NULL,
	sample_timestamp timestamptz NULL,
	mins_before_wake int4 NULL,
	"rule" text NULL,
	proximity_level text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_hrv_hrv_sdnn_ms_check CHECK ((hrv_sdnn_ms > (0)::numeric)),
	CONSTRAINT health_hrv_pkey PRIMARY KEY (date)
);
CREATE INDEX idx_health_hrv_measured_at ON public.health_hrv USING btree (measured_at);
CREATE INDEX idx_health_hrv_sample_timestamp ON public.health_hrv USING btree (sample_timestamp);


-- public.health_rhr definition

-- Drop table

-- DROP TABLE public.health_rhr;

CREATE TABLE public.health_rhr (
	"date" date NOT NULL,
	measured_at timestamptz NOT NULL,
	rhr_bpm int4 NOT NULL,
	"source" text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_rhr_pkey PRIMARY KEY (date),
	CONSTRAINT health_rhr_rhr_bpm_check CHECK ((rhr_bpm > 0))
);
CREATE INDEX idx_health_rhr_measured_at ON public.health_rhr USING btree (measured_at);


-- public.health_sleep definition

-- Drop table

-- DROP TABLE public.health_sleep;

CREATE TABLE public.health_sleep (
	"date" date NOT NULL,
	sleep_start timestamptz NULL,
	sleep_end timestamptz NULL,
	in_bed_start timestamptz NULL,
	in_bed_end timestamptz NULL,
	deep_sleep_hr numeric NULL,
	core_sleep_hr numeric NULL,
	rem_sleep_hr numeric NULL,
	awake_hr numeric NULL,
	total_sleep_hr numeric NULL,
	asleep_hr numeric NULL,
	in_bed_hr numeric NULL,
	sleep_score int4 NULL,
	duration_pts int4 NULL,
	consistency_pts int4 NULL,
	interruptions_pts int4 NULL,
	score_version text NULL,
	"source" text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_sleep_pkey PRIMARY KEY (date)
);


-- public.health_steps definition

-- Drop table

-- DROP TABLE public.health_steps;

CREATE TABLE public.health_steps (
	"date" date NOT NULL,
	measured_at timestamptz NOT NULL,
	steps int4 NOT NULL,
	"source" text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_steps_pkey PRIMARY KEY (date),
	CONSTRAINT health_steps_steps_check CHECK ((steps >= 0))
);
CREATE INDEX idx_health_steps_measured_at ON public.health_steps USING btree (measured_at);


-- public.health_vo2_max definition

-- Drop table

-- DROP TABLE public.health_vo2_max;

CREATE TABLE public.health_vo2_max (
	week_start date NOT NULL,
	measured_at timestamptz NOT NULL,
	vo2max numeric NOT NULL,
	"source" text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_vo2_max_pkey PRIMARY KEY (week_start),
	CONSTRAINT health_vo2_max_vo2max_check CHECK ((vo2max > (0)::numeric))
);
CREATE INDEX idx_health_vo2_max_measured_at ON public.health_vo2_max USING btree (measured_at);


-- public.health_weight definition

-- Drop table

-- DROP TABLE public.health_weight;

CREATE TABLE public.health_weight (
	"date" date NOT NULL,
	measured_at timestamptz NULL,
	weight_lb numeric NULL,
	body_fat_pct numeric NULL,
	lean_body_mass_lb numeric NULL,
	bmi numeric NULL,
	"source" text NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT health_weight_pkey PRIMARY KEY (date)
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
	request_type text DEFAULT 'full_sync'::text NOT NULL,
	activity_id int8 NULL,
	result_json jsonb NULL,
	CONSTRAINT ck_sync_request_type_target CHECK ((((request_type = 'full_sync'::text) AND (activity_id IS NULL)) OR ((request_type = 'activity_resync'::text) AND (activity_id IS NOT NULL) AND (activity_id > 0)))),
	CONSTRAINT sync_request_pkey PRIMARY KEY (id)
);
CREATE INDEX idx_sync_request_status_requested ON public.sync_request USING btree (status, requested_at_utc);
CREATE UNIQUE INDEX ux_sync_request_active_activity_resync ON public.sync_request USING btree (activity_id) WHERE ((request_type = 'activity_resync'::text) AND (status = ANY (ARRAY['pending'::text, 'running'::text])));


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


-- public.training_year definition

-- Drop table

-- DROP TABLE public.training_year;

CREATE TABLE public.training_year (
	calendar_year int4 NOT NULL,
	training_hours numeric(10, 2) NULL, -- Traditional training-hours metric used by the historical workbook and official hour records.
	strava_activity_hours numeric(10, 2) NULL, -- Sum of strava_activities.moving_sec divided by 3600 for the calendar year.
	active_days int4 NULL,
	activity_count int4 NULL,
	total_distance_mi numeric(12, 2) NULL,
	cycling_distance_mi numeric(12, 2) NULL,
	total_elevation_ft int8 NULL,
	bike_elevation_ft int8 NULL,
	ride_count int4 NULL,
	ride_days int4 NULL,
	ski_days int4 NULL,
	strength_sessions int4 NULL,
	mobility_sessions int4 NULL,
	walk_count int4 NULL,
	hike_count int4 NULL,
	weight_min_lb numeric(6, 2) NULL,
	weight_max_lb numeric(6, 2) NULL,
	weight_avg_lb numeric(6, 2) NULL,
	race_count int4 NULL,
	is_ytd bool DEFAULT false NOT NULL,
	through_date date NULL,
	coverage_status text DEFAULT 'complete_calendar'::text NOT NULL,
	source_first_date date NULL,
	source_last_date date NULL,
	months_with_activity int4 NULL,
	calculated_at timestamptz NULL,
	notes text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT training_year_active_days_check CHECK (((active_days IS NULL) OR (active_days >= 0))),
	CONSTRAINT training_year_activity_count_check CHECK (((activity_count IS NULL) OR (activity_count >= 0))),
	CONSTRAINT training_year_bike_elevation_check CHECK (((bike_elevation_ft IS NULL) OR (bike_elevation_ft >= 0))),
	CONSTRAINT training_year_calendar_year_check CHECK (((calendar_year >= 1900) AND (calendar_year <= 2200))),
	CONSTRAINT training_year_coverage_status_check CHECK ((coverage_status = ANY (ARRAY['historical_import'::text, 'complete_calendar'::text, 'partial_calendar'::text, 'missing_months'::text, 'ytd'::text]))),
	CONSTRAINT training_year_cycling_distance_check CHECK (((cycling_distance_mi IS NULL) OR (cycling_distance_mi >= (0)::numeric))),
	CONSTRAINT training_year_hike_count_check CHECK (((hike_count IS NULL) OR (hike_count >= 0))),
	CONSTRAINT training_year_mobility_sessions_check CHECK (((mobility_sessions IS NULL) OR (mobility_sessions >= 0))),
	CONSTRAINT training_year_months_check CHECK (((months_with_activity IS NULL) OR ((months_with_activity >= 0) AND (months_with_activity <= 12)))),
	CONSTRAINT training_year_pkey PRIMARY KEY (calendar_year),
	CONSTRAINT training_year_race_count_check CHECK (((race_count IS NULL) OR (race_count >= 0))),
	CONSTRAINT training_year_ride_count_check CHECK (((ride_count IS NULL) OR (ride_count >= 0))),
	CONSTRAINT training_year_ride_days_check CHECK (((ride_days IS NULL) OR (ride_days >= 0))),
	CONSTRAINT training_year_ski_days_check CHECK (((ski_days IS NULL) OR (ski_days >= 0))),
	CONSTRAINT training_year_source_date_order_check CHECK (((source_first_date IS NULL) OR (source_last_date IS NULL) OR (source_last_date >= source_first_date))),
	CONSTRAINT training_year_source_dates_match_year_check CHECK ((((source_first_date IS NULL) OR ((EXTRACT(year FROM source_first_date))::integer = calendar_year)) AND ((source_last_date IS NULL) OR ((EXTRACT(year FROM source_last_date))::integer = calendar_year)))),
	CONSTRAINT training_year_strava_hours_check CHECK (((strava_activity_hours IS NULL) OR (strava_activity_hours >= (0)::numeric))),
	CONSTRAINT training_year_strength_sessions_check CHECK (((strength_sessions IS NULL) OR (strength_sessions >= 0))),
	CONSTRAINT training_year_total_distance_check CHECK (((total_distance_mi IS NULL) OR (total_distance_mi >= (0)::numeric))),
	CONSTRAINT training_year_total_elevation_check CHECK (((total_elevation_ft IS NULL) OR (total_elevation_ft >= 0))),
	CONSTRAINT training_year_training_hours_check CHECK (((training_hours IS NULL) OR (training_hours >= (0)::numeric))),
	CONSTRAINT training_year_walk_count_check CHECK (((walk_count IS NULL) OR (walk_count >= 0))),
	CONSTRAINT training_year_weight_avg_check CHECK (((weight_avg_lb IS NULL) OR (weight_avg_lb > (0)::numeric))),
	CONSTRAINT training_year_weight_avg_range_check CHECK (((weight_avg_lb IS NULL) OR (weight_min_lb IS NULL) OR (weight_max_lb IS NULL) OR ((weight_avg_lb >= weight_min_lb) AND (weight_avg_lb <= weight_max_lb)))),
	CONSTRAINT training_year_weight_max_check CHECK (((weight_max_lb IS NULL) OR (weight_max_lb > (0)::numeric))),
	CONSTRAINT training_year_weight_min_check CHECK (((weight_min_lb IS NULL) OR (weight_min_lb > (0)::numeric))),
	CONSTRAINT training_year_weight_range_check CHECK (((weight_min_lb IS NULL) OR (weight_max_lb IS NULL) OR (weight_max_lb >= weight_min_lb))),
	CONSTRAINT training_year_ytd_check CHECK ((((is_ytd = false) AND (through_date IS NULL) AND (coverage_status <> 'ytd'::text)) OR ((is_ytd = true) AND (through_date IS NOT NULL) AND ((EXTRACT(year FROM through_date))::integer = calendar_year) AND (coverage_status = 'ytd'::text))))
);
CREATE INDEX training_year_coverage_idx ON public.training_year USING btree (coverage_status, calendar_year DESC);
COMMENT ON TABLE public.training_year IS 'One row per calendar year containing imported and calculated annual training facts.';

-- Column comments

COMMENT ON COLUMN public.training_year.training_hours IS 'Traditional training-hours metric used by the historical workbook and official hour records.';
COMMENT ON COLUMN public.training_year.strava_activity_hours IS 'Sum of strava_activities.moving_sec divided by 3600 for the calendar year.';


-- public.training_year_run definition

-- Drop table

-- DROP TABLE public.training_year_run;

CREATE TABLE public.training_year_run (
	training_year_run_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	calendar_year int4 NOT NULL,
	requested_at_utc timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	requested_by text DEFAULT 'settings'::text NOT NULL,
	calculation_mode text NOT NULL,
	apply_changes bool DEFAULT false NOT NULL,
	source_first_date date NULL,
	source_last_date date NULL,
	activity_count int4 NULL,
	months_with_activity int4 NULL,
	status text DEFAULT 'pending'::text NOT NULL,
	message text NULL, -- Sanitized status text only; must not contain SQL, stack traces, credentials, tokens, or environment values.
	started_at_utc timestamptz NULL,
	completed_at_utc timestamptz NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT training_year_run_activity_count_check CHECK (((activity_count IS NULL) OR (activity_count >= 0))),
	CONSTRAINT training_year_run_apply_mode_check CHECK ((((calculation_mode = 'preview'::text) AND (apply_changes = false)) OR (calculation_mode = ANY (ARRAY['calculate'::text, 'finalize'::text])))),
	CONSTRAINT training_year_run_calendar_year_check CHECK (((calendar_year >= 1900) AND (calendar_year <= 2200))),
	CONSTRAINT training_year_run_mode_check CHECK ((calculation_mode = ANY (ARRAY['preview'::text, 'calculate'::text, 'finalize'::text]))),
	CONSTRAINT training_year_run_months_check CHECK (((months_with_activity IS NULL) OR ((months_with_activity >= 0) AND (months_with_activity <= 12)))),
	CONSTRAINT training_year_run_pkey PRIMARY KEY (training_year_run_id),
	CONSTRAINT training_year_run_requested_by_check CHECK ((btrim(requested_by) <> ''::text)),
	CONSTRAINT training_year_run_source_date_order_check CHECK (((source_first_date IS NULL) OR (source_last_date IS NULL) OR (source_last_date >= source_first_date))),
	CONSTRAINT training_year_run_source_dates_match_year_check CHECK ((((source_first_date IS NULL) OR ((EXTRACT(year FROM source_first_date))::integer = calendar_year)) AND ((source_last_date IS NULL) OR ((EXTRACT(year FROM source_last_date))::integer = calendar_year)))),
	CONSTRAINT training_year_run_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text]))),
	CONSTRAINT training_year_run_timestamp_order_check CHECK ((((started_at_utc IS NULL) OR (started_at_utc >= requested_at_utc)) AND ((completed_at_utc IS NULL) OR (started_at_utc IS NOT NULL)) AND ((completed_at_utc IS NULL) OR (completed_at_utc >= started_at_utc))))
);
CREATE INDEX training_year_run_status_requested_idx ON public.training_year_run USING btree (status, requested_at_utc DESC);
CREATE INDEX training_year_run_year_requested_idx ON public.training_year_run USING btree (calendar_year, requested_at_utc DESC);
COMMENT ON TABLE public.training_year_run IS 'Audit history for Yearly preview, calculation, and finalization requests.';

-- Column comments

COMMENT ON COLUMN public.training_year_run.message IS 'Sanitized status text only; must not contain SQL, stack traces, credentials, tokens, or environment values.';


-- public.weekly_audit definition

-- Drop table

-- DROP TABLE public.weekly_audit;

CREATE TABLE public.weekly_audit (
	week_start date NOT NULL,
	audit_version text DEFAULT 'v1'::text NOT NULL,
	overall_grade text NULL,
	green_count int4 DEFAULT 0 NOT NULL,
	yellow_count int4 DEFAULT 0 NOT NULL,
	red_count int4 DEFAULT 0 NOT NULL,
	audit_summary text NULL,
	next_week_action text NULL,
	"source" text DEFAULT 'computed'::text NOT NULL,
	computed_at timestamptz NULL,
	reviewed_at timestamptz NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT weekly_audit_pkey PRIMARY KEY (week_start)
);


-- public.weekly_audit_item definition

-- Drop table

-- DROP TABLE public.weekly_audit_item;

CREATE TABLE public.weekly_audit_item (
	id bigserial NOT NULL,
	week_start date NOT NULL,
	item_key text NOT NULL,
	item_label text NOT NULL,
	status text NOT NULL,
	summary text NULL,
	sort_order int4 NOT NULL,
	"source" text DEFAULT 'computed'::text NOT NULL,
	evidence_json jsonb NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT uq_weekly_audit_item_week_key UNIQUE (week_start, item_key),
	CONSTRAINT weekly_audit_item_pkey PRIMARY KEY (id)
);


-- public.weekly_commentary definition

-- Drop table

-- DROP TABLE public.weekly_commentary;

CREATE TABLE public.weekly_commentary (
	week_start date NOT NULL,
	week_type text NULL,
	"event" text NULL,
	planned_focus text NULL,
	actual_focus text NULL,
	weekly_comment text NULL,
	risk_note text NULL,
	coach_note text NULL,
	task_note text NULL,
	lesson_learned text NULL,
	status_override text NULL,
	is_travel_week bool DEFAULT false NOT NULL,
	is_sick_week bool DEFAULT false NOT NULL,
	is_injury_week bool DEFAULT false NOT NULL,
	is_bike_park_week bool DEFAULT false NOT NULL,
	is_recovery_week bool DEFAULT false NOT NULL,
	is_goal_week bool DEFAULT false NOT NULL,
	hide_from_dashboard bool DEFAULT false NOT NULL,
	display_priority int4 DEFAULT 0 NOT NULL,
	created_at timestamptz DEFAULT now() NOT NULL,
	updated_at timestamptz DEFAULT now() NOT NULL,
	CONSTRAINT weekly_commentary_pkey PRIMARY KEY (week_start)
);
CREATE INDEX idx_weekly_commentary_event ON public.weekly_commentary USING btree (event);
CREATE INDEX idx_weekly_commentary_flags ON public.weekly_commentary USING btree (is_travel_week, is_sick_week, is_injury_week, is_bike_park_week, is_recovery_week);
CREATE INDEX idx_weekly_commentary_week_type ON public.weekly_commentary USING btree (week_type);


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


-- public.gear_component definition

-- Drop table

-- DROP TABLE public.gear_component;

CREATE TABLE public.gear_component (
	gear_component_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	gear_id text NOT NULL,
	component_key text NOT NULL,
	component_name text NOT NULL,
	component_group text NOT NULL,
	"position" text NULL,
	track_life bool DEFAULT false NOT NULL,
	track_service bool DEFAULT true NOT NULL,
	preferred_metric text DEFAULT 'mixed'::text NOT NULL,
	service_interval_miles numeric(12, 2) NULL,
	service_interval_hours numeric(12, 2) NULL,
	service_interval_days int4 NULL,
	service_interval_rides int4 NULL,
	warning_percent numeric(5, 2) DEFAULT 80.00 NOT NULL,
	display_order int4 DEFAULT 100 NOT NULL,
	active bool DEFAULT true NOT NULL,
	notes text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT gear_component_gear_key_unique UNIQUE (gear_id, component_key),
	CONSTRAINT gear_component_group_not_blank CHECK ((btrim(component_group) <> ''::text)),
	CONSTRAINT gear_component_interval_days_check CHECK (((service_interval_days IS NULL) OR (service_interval_days > 0))),
	CONSTRAINT gear_component_interval_hours_check CHECK (((service_interval_hours IS NULL) OR (service_interval_hours > (0)::numeric))),
	CONSTRAINT gear_component_interval_miles_check CHECK (((service_interval_miles IS NULL) OR (service_interval_miles > (0)::numeric))),
	CONSTRAINT gear_component_interval_rides_check CHECK (((service_interval_rides IS NULL) OR (service_interval_rides > 0))),
	CONSTRAINT gear_component_key_not_blank CHECK ((btrim(component_key) <> ''::text)),
	CONSTRAINT gear_component_name_not_blank CHECK ((btrim(component_name) <> ''::text)),
	CONSTRAINT gear_component_pkey PRIMARY KEY (gear_component_id),
	CONSTRAINT gear_component_preferred_metric_check CHECK ((preferred_metric = ANY (ARRAY['miles'::text, 'hours'::text, 'days'::text, 'rides'::text, 'mixed'::text, 'inspection'::text]))),
	CONSTRAINT gear_component_warning_percent_check CHECK (((warning_percent > (0)::numeric) AND (warning_percent <= (100)::numeric))),
	CONSTRAINT gear_component_gear_fkey FOREIGN KEY (gear_id) REFERENCES public.gear(gear_id) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX gear_component_gear_active_order_idx ON public.gear_component USING btree (gear_id, active, display_order, component_name);


-- public.gear_service_event definition

-- Drop table

-- DROP TABLE public.gear_service_event;

CREATE TABLE public.gear_service_event (
	service_event_id int8 GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE) NOT NULL,
	gear_component_id int8 NOT NULL,
	gear_id text NOT NULL,
	service_date date NOT NULL,
	"action" text NOT NULL,
	product_name text NULL,
	manufacturer text NULL,
	model text NULL,
	notes text NULL,
	"cost" numeric(12, 2) NULL,
	odometer_miles numeric(12, 2) NULL,
	odometer_hours numeric(12, 2) NULL,
	odometer_rides int4 NULL,
	odometer_elevation_ft int8 NULL,
	performed_by text NULL,
	service_location text NULL,
	"source" text DEFAULT 'app'::text NOT NULL,
	source_reference text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT gear_service_event_action_not_blank CHECK ((btrim(action) <> ''::text)),
	CONSTRAINT gear_service_event_cost_check CHECK (((cost IS NULL) OR (cost >= (0)::numeric))),
	CONSTRAINT gear_service_event_odometer_elevation_check CHECK (((odometer_elevation_ft IS NULL) OR (odometer_elevation_ft >= 0))),
	CONSTRAINT gear_service_event_odometer_hours_check CHECK (((odometer_hours IS NULL) OR (odometer_hours >= (0)::numeric))),
	CONSTRAINT gear_service_event_odometer_miles_check CHECK (((odometer_miles IS NULL) OR (odometer_miles >= (0)::numeric))),
	CONSTRAINT gear_service_event_odometer_rides_check CHECK (((odometer_rides IS NULL) OR (odometer_rides >= 0))),
	CONSTRAINT gear_service_event_pkey PRIMARY KEY (service_event_id),
	CONSTRAINT gear_service_event_source_check CHECK ((source = ANY (ARRAY['app'::text, 'excel_import'::text, 'manual_sql'::text, 'api'::text]))),
	CONSTRAINT gear_service_event_component_fkey FOREIGN KEY (gear_component_id) REFERENCES public.gear_component(gear_component_id) ON DELETE RESTRICT ON UPDATE CASCADE,
	CONSTRAINT gear_service_event_gear_fkey FOREIGN KEY (gear_id) REFERENCES public.gear(gear_id) ON DELETE RESTRICT ON UPDATE CASCADE
);
CREATE INDEX gear_service_event_action_idx ON public.gear_service_event USING btree (action, service_date DESC);
CREATE INDEX gear_service_event_component_date_idx ON public.gear_service_event USING btree (gear_component_id, service_date DESC, service_event_id DESC);
CREATE INDEX gear_service_event_gear_date_idx ON public.gear_service_event USING btree (gear_id, service_date DESC, service_event_id DESC);


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


-- public.training_year_commentary definition

-- Drop table

-- DROP TABLE public.training_year_commentary;

CREATE TABLE public.training_year_commentary (
	calendar_year int4 NOT NULL,
	good_summary text NULL,
	bad_summary text NULL,
	annual_summary text NULL,
	"source" text DEFAULT 'excel_import'::text NOT NULL,
	source_reference text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT training_year_commentary_pkey PRIMARY KEY (calendar_year),
	CONSTRAINT training_year_commentary_source_check CHECK ((source = ANY (ARRAY['excel_import'::text, 'manual'::text, 'mixed'::text]))),
	CONSTRAINT training_year_commentary_year_fkey FOREIGN KEY (calendar_year) REFERENCES public.training_year(calendar_year) ON DELETE CASCADE ON UPDATE CASCADE
);
COMMENT ON TABLE public.training_year_commentary IS 'Yearly Good, Bad, and annual narrative content kept separate from numerical facts.';


-- public.training_year_metric_source definition

-- Drop table

-- DROP TABLE public.training_year_metric_source;

CREATE TABLE public.training_year_metric_source (
	calendar_year int4 NOT NULL,
	metric_key text NOT NULL,
	"source" text NOT NULL,
	source_reference text NULL,
	calculated_at timestamptz NULL,
	notes text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT training_year_metric_source_key_check CHECK ((btrim(metric_key) <> ''::text)),
	CONSTRAINT training_year_metric_source_pkey PRIMARY KEY (calendar_year, metric_key),
	CONSTRAINT training_year_metric_source_source_check CHECK ((source = ANY (ARRAY['excel_import'::text, 'strava_rollup'::text, 'health_rollup'::text, 'manual'::text]))),
	CONSTRAINT training_year_metric_source_year_fkey FOREIGN KEY (calendar_year) REFERENCES public.training_year(calendar_year) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX training_year_metric_source_metric_year_idx ON public.training_year_metric_source USING btree (metric_key, calendar_year DESC);
COMMENT ON TABLE public.training_year_metric_source IS 'Metric-level provenance identifying the authoritative source for each annual metric.';


-- public.training_year_month definition

-- Drop table

-- DROP TABLE public.training_year_month;

CREATE TABLE public.training_year_month (
	calendar_year int4 NOT NULL,
	calendar_month int4 NOT NULL,
	training_hours numeric(8, 2) NULL,
	strava_activity_hours numeric(8, 2) NULL,
	active_days int4 NULL,
	activity_count int4 NULL,
	total_distance_mi numeric(10, 2) NULL,
	cycling_distance_mi numeric(10, 2) NULL,
	total_elevation_ft int8 NULL,
	bike_elevation_ft int8 NULL,
	ride_count int4 NULL,
	ride_days int4 NULL,
	ski_days int4 NULL,
	source_first_date date NULL,
	source_last_date date NULL,
	is_complete bool DEFAULT true NOT NULL,
	calculated_at timestamptz NULL,
	notes text NULL,
	created_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	updated_at timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL,
	CONSTRAINT training_year_month_active_days_check CHECK (((active_days IS NULL) OR (active_days >= 0))),
	CONSTRAINT training_year_month_activity_count_check CHECK (((activity_count IS NULL) OR (activity_count >= 0))),
	CONSTRAINT training_year_month_bike_elevation_check CHECK (((bike_elevation_ft IS NULL) OR (bike_elevation_ft >= 0))),
	CONSTRAINT training_year_month_cycling_distance_check CHECK (((cycling_distance_mi IS NULL) OR (cycling_distance_mi >= (0)::numeric))),
	CONSTRAINT training_year_month_month_check CHECK (((calendar_month >= 1) AND (calendar_month <= 12))),
	CONSTRAINT training_year_month_pkey PRIMARY KEY (calendar_year, calendar_month),
	CONSTRAINT training_year_month_ride_count_check CHECK (((ride_count IS NULL) OR (ride_count >= 0))),
	CONSTRAINT training_year_month_ride_days_check CHECK (((ride_days IS NULL) OR (ride_days >= 0))),
	CONSTRAINT training_year_month_ski_days_check CHECK (((ski_days IS NULL) OR (ski_days >= 0))),
	CONSTRAINT training_year_month_source_date_order_check CHECK (((source_first_date IS NULL) OR (source_last_date IS NULL) OR (source_last_date >= source_first_date))),
	CONSTRAINT training_year_month_source_dates_match_period_check CHECK ((((source_first_date IS NULL) OR (((EXTRACT(year FROM source_first_date))::integer = calendar_year) AND ((EXTRACT(month FROM source_first_date))::integer = calendar_month))) AND ((source_last_date IS NULL) OR (((EXTRACT(year FROM source_last_date))::integer = calendar_year) AND ((EXTRACT(month FROM source_last_date))::integer = calendar_month))))),
	CONSTRAINT training_year_month_strava_hours_check CHECK (((strava_activity_hours IS NULL) OR (strava_activity_hours >= (0)::numeric))),
	CONSTRAINT training_year_month_total_distance_check CHECK (((total_distance_mi IS NULL) OR (total_distance_mi >= (0)::numeric))),
	CONSTRAINT training_year_month_total_elevation_check CHECK (((total_elevation_ft IS NULL) OR (total_elevation_ft >= 0))),
	CONSTRAINT training_year_month_training_hours_check CHECK (((training_hours IS NULL) OR (training_hours >= (0)::numeric))),
	CONSTRAINT training_year_month_year_fkey FOREIGN KEY (calendar_year) REFERENCES public.training_year(calendar_year) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX training_year_month_month_year_idx ON public.training_year_month USING btree (calendar_month, calendar_year DESC);
COMMENT ON TABLE public.training_year_month IS 'One row per calendar month containing imported and calculated monthly training facts.';


-- public.weekly_zone_summary source

CREATE OR REPLACE VIEW public.weekly_zone_summary
AS WITH daily_zone_source AS (
         SELECT (daily_training.date - (EXTRACT(isodow FROM daily_training.date)::integer - 1)::double precision * '1 day'::interval)::date AS week_start,
            COALESCE(daily_training.ride_count, 0) AS ride_count,
            COALESCE(daily_training.z1_sec, 0) AS z1_sec,
            COALESCE(daily_training.z2_sec, 0) AS z2_sec,
            COALESCE(daily_training.z3_sec, 0) AS z3_sec,
            COALESCE(daily_training.z4_sec, 0) AS z4_sec,
            COALESCE(daily_training.z5_sec, 0) AS z5_sec,
            COALESCE(daily_training.stream_moving_sec, 0) AS stream_moving_sec
           FROM daily_training
        ), weekly AS (
         SELECT daily_zone_source.week_start,
            daily_zone_source.week_start + 6 AS week_end,
            sum(daily_zone_source.ride_count)::integer AS ride_count,
            sum(daily_zone_source.z1_sec) AS z1_sec,
            sum(daily_zone_source.z2_sec) AS z2_sec,
            sum(daily_zone_source.z3_sec) AS z3_sec,
            sum(daily_zone_source.z4_sec) AS z4_sec,
            sum(daily_zone_source.z5_sec) AS z5_sec,
            sum(daily_zone_source.stream_moving_sec) AS stream_moving_sec
           FROM daily_zone_source
          GROUP BY daily_zone_source.week_start
        ), calc AS (
         SELECT weekly.week_start,
            weekly.week_end,
            weekly.ride_count,
            weekly.z1_sec,
            weekly.z2_sec,
            weekly.z3_sec,
            weekly.z4_sec,
            weekly.z5_sec,
            weekly.stream_moving_sec,
            weekly.z1_sec + weekly.z2_sec AS z1_z2_sec,
            weekly.z4_sec + weekly.z5_sec AS z4_z5_sec,
            weekly.z1_sec + weekly.z2_sec + weekly.z3_sec + weekly.z4_sec + weekly.z5_sec AS zone_total_sec
           FROM weekly
        )
 SELECT week_start,
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
            WHEN zone_total_sec > 0 THEN round(z1_z2_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer
            ELSE NULL::integer
        END AS z1_z2_pct,
        CASE
            WHEN zone_total_sec > 0 THEN round(z3_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer
            ELSE NULL::integer
        END AS z3_pct,
        CASE
            WHEN zone_total_sec > 0 THEN round(z4_z5_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer
            ELSE NULL::integer
        END AS z4_z5_pct,
        CASE
            WHEN stream_moving_sec > 0 THEN round(zone_total_sec::numeric / stream_moving_sec::numeric * 100::numeric, 0)::integer
            ELSE NULL::integer
        END AS zone_coverage_pct,
    (((zone_total_sec / 3600)::text) || ':'::text) || lpad((zone_total_sec % 3600::bigint / 60)::text, 2, '0'::text) AS ride_time_hhmm,
    (((z1_z2_sec / 3600)::text) || ':'::text) || lpad((z1_z2_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z1_z2_hhmm,
    (((z3_sec / 3600)::text) || ':'::text) || lpad((z3_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z3_hhmm,
    (((z4_z5_sec / 3600)::text) || ':'::text) || lpad((z4_z5_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z4_z5_hhmm,
    (((z1_sec / 3600)::text) || ':'::text) || lpad((z1_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z1_hhmm,
    (((z2_sec / 3600)::text) || ':'::text) || lpad((z2_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z2_hhmm,
    (((z4_sec / 3600)::text) || ':'::text) || lpad((z4_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z4_hhmm,
    (((z5_sec / 3600)::text) || ':'::text) || lpad((z5_sec % 3600::bigint / 60)::text, 2, '0'::text) AS z5_hhmm,
        CASE
            WHEN zone_total_sec = 0 THEN 'No zone data'::text
            WHEN round(z4_z5_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer > 20 THEN 'High intensity-heavy'::text
            WHEN round(z3_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer > 30 THEN 'Tempo-heavy'::text
            WHEN round(z1_z2_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer < 60 THEN 'Low aerobic share'::text
            WHEN round(z1_z2_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer >= 60 AND round(z1_z2_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer <= 80 AND round(z3_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer >= 10 AND round(z3_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer <= 30 AND round(z4_z5_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer <= 10 THEN 'Target distribution'::text
            WHEN round(z1_z2_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer > 80 AND round(z4_z5_sec::numeric / zone_total_sec::numeric * 100::numeric, 0)::integer <= 10 THEN 'Easy-heavy'::text
            ELSE 'Review'::text
        END AS zone_flag
   FROM calc
  WHERE zone_total_sec > 0;