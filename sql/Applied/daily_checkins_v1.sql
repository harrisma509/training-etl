-- Daily Check-ins persistence contract v1.
-- Manual application only: review this script and execute it through DBeaver.
-- Do not apply it through the application, a migration tool, or an automated deploy.
-- This table is independent from rebuildable daily_training rows.

BEGIN;

CREATE TABLE IF NOT EXISTS public.daily_checkin (
    checkin_date date NOT NULL,
    overall_status text NOT NULL,
    note text NOT NULL,
    readiness smallint NULL,
    energy smallint NULL,
    soreness smallint NULL,
    pain smallint NULL,
    physical_labor text NULL,
    handling_quality text NULL,
    is_travel boolean NOT NULL DEFAULT false,
    is_sick boolean NOT NULL DEFAULT false,
    is_injury boolean NOT NULL DEFAULT false,
    is_bike_park boolean NOT NULL DEFAULT false,
    is_recovery boolean NOT NULL DEFAULT false,
    is_goal_event boolean NOT NULL DEFAULT false,
    is_bad_weather boolean NOT NULL DEFAULT false,
    is_high_life_stress boolean NOT NULL DEFAULT false,
    is_lost boolean NOT NULL DEFAULT false,
    is_gear boolean NOT NULL DEFAULT false,
    is_crash boolean NOT NULL DEFAULT false,
    is_group_ride boolean NOT NULL DEFAULT false,
    is_sore boolean NOT NULL DEFAULT false,
    is_tired boolean NOT NULL DEFAULT false,
    is_poor_sleep boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT daily_checkin_checkin_date_not_null NOT NULL checkin_date,
    CONSTRAINT daily_checkin_overall_status_not_null NOT NULL overall_status,
    CONSTRAINT daily_checkin_note_not_null NOT NULL note,
    CONSTRAINT daily_checkin_overall_status_check CHECK (overall_status IN ('good', 'mixed', 'poor')),
    CONSTRAINT daily_checkin_note_not_blank_check CHECK (btrim(note) <> ''),
    CONSTRAINT daily_checkin_note_length_check CHECK (char_length(note) <= 1000),
    CONSTRAINT daily_checkin_readiness_range_check CHECK (readiness IS NULL OR readiness BETWEEN 1 AND 5),
    CONSTRAINT daily_checkin_energy_range_check CHECK (energy IS NULL OR energy BETWEEN 1 AND 5),
    CONSTRAINT daily_checkin_soreness_range_check CHECK (soreness IS NULL OR soreness BETWEEN 0 AND 4),
    CONSTRAINT daily_checkin_pain_range_check CHECK (pain IS NULL OR pain BETWEEN 0 AND 4),
    CONSTRAINT daily_checkin_physical_labor_check CHECK (physical_labor IS NULL OR physical_labor IN ('none', 'light', 'moderate', 'heavy')),
    CONSTRAINT daily_checkin_handling_quality_check CHECK (handling_quality IS NULL OR handling_quality IN ('sharp', 'normal', 'off')),
    CONSTRAINT daily_checkin_updated_at_after_created_at_check CHECK (updated_at >= created_at),
    CONSTRAINT daily_checkin_pkey PRIMARY KEY (checkin_date)
);

COMMIT;
