import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "sql" / "Applied" / "plan_core_v1_slice_1.sql"
SCHEMA = ROOT / "sql" / "training_postgress_db_schema.sql"
PLAN_TABLES = (
    "plan_category",
    "plan_prescription",
    "plan_prescription_segment",
    "plan_template",
    "plan_batch",
    "plan_item",
)


def _table_names(sql):
    return re.findall(r"(?im)^CREATE TABLE public\.(plan_[a-z_]+)\s*\(", sql)


def _table_body(sql, table_name):
    match = re.search(
        rf"(?ims)^CREATE TABLE public\.{re.escape(table_name)}\s*\((.*?)^\);",
        sql,
    )
    assert match is not None, f"missing definition for {table_name}"
    return match.group(1)


def _column_declarations(table_body):
    declarations = []
    for line in table_body.splitlines():
        if not line.startswith("    ") or line.startswith("        "):
            continue
        line = line.strip().rstrip(",")
        if line and not line.startswith("CONSTRAINT "):
            declarations.append(line)
    return declarations


def _plan_indexes(sql):
    return re.findall(
        r"(?ims)^CREATE (?:UNIQUE )?INDEX plan_[a-z_]+\s+ON public\.plan_[a-z_]+"
        r".*?;",
        sql,
    )


def _plan_constraints(sql):
    bodies = "\n".join(_table_body(sql, table_name) for table_name in PLAN_TABLES)
    return set(re.findall(r"\bCONSTRAINT\s+([a-z_]+)", bodies))


EXPECTED_COLUMNS = {
    "plan_category": (
        "plan_category_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL",
        "category_key text NOT NULL",
        "category_name text NOT NULL",
        "color_key text NULL",
        "icon_key text NULL",
        "sort_order integer DEFAULT 0 NOT NULL",
        "is_active boolean DEFAULT true NOT NULL",
        "created_at timestamptz DEFAULT now() NOT NULL",
        "updated_at timestamptz DEFAULT now() NOT NULL",
    ),
    "plan_prescription": (
        "plan_prescription_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL",
        "owner_kind text NOT NULL",
        "title text NOT NULL",
        "description text NULL",
        "sport_type text NULL",
        "activity_category text NULL",
        "trainer boolean NULL",
        "target_duration_min numeric(7, 2) NULL",
        "target_load integer NULL",
        "target_load_source text NULL",
        "target_distance_mi numeric(10, 3) NULL",
        "target_elevation_ft integer NULL",
        "instruction_text text NULL",
        "created_at timestamptz DEFAULT now() NOT NULL",
        "updated_at timestamptz DEFAULT now() NOT NULL",
    ),
    "plan_prescription_segment": (
        "plan_prescription_segment_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL",
        "plan_prescription_id bigint NOT NULL",
        "segment_order smallint NOT NULL",
        "segment_name text NULL",
        "repeat_group_key smallint NULL",
        "repeat_count smallint DEFAULT 1 NOT NULL",
        "target_duration_min numeric(7, 2) NULL",
        "target_metric text DEFAULT 'none' NOT NULL",
        "zone_min smallint NULL",
        "zone_max smallint NULL",
        "target_value_min numeric(8, 2) NULL",
        "target_value_max numeric(8, 2) NULL",
        "instruction_text text NULL",
        "created_at timestamptz DEFAULT now() NOT NULL",
        "updated_at timestamptz DEFAULT now() NOT NULL",
    ),
    "plan_template": (
        "plan_template_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL",
        "plan_category_id bigint NOT NULL",
        "plan_prescription_id bigint NOT NULL",
        "prescription_owner_kind text DEFAULT 'template' NOT NULL",
        "template_name text NOT NULL",
        "template_description text NULL",
        "sort_order integer DEFAULT 0 NOT NULL",
        "is_active boolean DEFAULT true NOT NULL",
        "created_at timestamptz DEFAULT now() NOT NULL",
        "updated_at timestamptz DEFAULT now() NOT NULL",
    ),
    "plan_batch": (
        "plan_batch_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL",
        "batch_type text NOT NULL",
        "batch_status text DEFAULT 'open' NOT NULL",
        "batch_name text NULL",
        "range_start date NULL",
        "range_end date NULL",
        "source_reference text NULL",
        "idempotency_key text NULL",
        "created_by text DEFAULT 'user' NOT NULL",
        "created_at timestamptz DEFAULT now() NOT NULL",
        "updated_at timestamptz DEFAULT now() NOT NULL",
        "committed_at timestamptz NULL",
        "discarded_at timestamptz NULL",
    ),
    "plan_item": (
        "plan_item_id bigint GENERATED ALWAYS AS IDENTITY NOT NULL",
        "plan_batch_id bigint NULL",
        "source_template_id bigint NULL",
        "plan_category_id bigint NOT NULL",
        "plan_prescription_id bigint NOT NULL",
        "prescription_owner_kind text DEFAULT 'item' NOT NULL",
        "planned_date date NOT NULL",
        "sort_order integer DEFAULT 0 NOT NULL",
        "item_state text NOT NULL",
        "item_source text DEFAULT 'manual' NOT NULL",
        "user_note text NULL",
        "created_at timestamptz DEFAULT now() NOT NULL",
        "updated_at timestamptz DEFAULT now() NOT NULL",
        "committed_at timestamptz NULL",
        "cancelled_at timestamptz NULL",
    ),
}

EXPECTED_CONSTRAINTS = {
    "plan_category_pkey",
    "plan_category_category_key_key",
    "plan_category_category_key_check",
    "plan_category_category_name_check",
    "plan_category_sort_order_check",
    "plan_prescription_pkey",
    "plan_prescription_id_owner_kind_key",
    "plan_prescription_owner_kind_check",
    "plan_prescription_title_check",
    "plan_prescription_sport_type_check",
    "plan_prescription_activity_category_check",
    "plan_prescription_target_load_source_check",
    "plan_prescription_target_duration_check",
    "plan_prescription_target_load_check",
    "plan_prescription_target_distance_check",
    "plan_prescription_target_elevation_check",
    "plan_prescription_segment_pkey",
    "plan_prescription_segment_prescription_order_key",
    "plan_prescription_segment_prescription_fkey",
    "plan_prescription_segment_order_check",
    "plan_prescription_segment_repeat_count_check",
    "plan_prescription_segment_repeat_group_key_check",
    "plan_prescription_segment_repeat_group_check",
    "plan_prescription_segment_target_duration_check",
    "plan_prescription_segment_zone_bounds_check",
    "plan_prescription_segment_target_values_check",
    "plan_prescription_segment_target_exclusive_check",
    "plan_prescription_segment_target_metric_check",
    "plan_prescription_segment_target_consistency_check",
    "plan_prescription_segment_content_check",
    "plan_template_pkey",
    "plan_template_prescription_id_key",
    "plan_template_category_fkey",
    "plan_template_prescription_owner_fkey",
    "plan_template_prescription_owner_kind_check",
    "plan_template_name_check",
    "plan_template_sort_order_check",
    "plan_batch_pkey",
    "plan_batch_type_check",
    "plan_batch_status_check",
    "plan_batch_idempotency_key_check",
    "plan_batch_created_by_check",
    "plan_batch_range_check",
    "plan_batch_terminal_times_check",
    "plan_batch_time_order_check",
    "plan_batch_updated_at_check",
    "plan_item_pkey",
    "plan_item_prescription_id_key",
    "plan_item_source_check",
    "plan_item_batch_fkey",
    "plan_item_source_template_fkey",
    "plan_item_category_fkey",
    "plan_item_prescription_owner_fkey",
    "plan_item_prescription_owner_kind_check",
    "plan_item_state_check",
    "plan_item_lifecycle_times_check",
    "plan_item_time_order_check",
    "plan_item_updated_at_check",
    "plan_item_sort_order_check",
}

EXPECTED_INDEX_NAMES = {
    "plan_category_active_order_idx",
    "plan_template_category_order_idx",
    "plan_batch_idempotency_key_uidx",
    "plan_batch_open_updated_idx",
    "plan_item_calendar_idx",
    "plan_item_batch_idx",
}


def test_plan_migration_and_canonical_schema_have_exactly_six_tables_in_order():
    migration = MIGRATION.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    assert _table_names(migration) == list(PLAN_TABLES)
    assert _table_names(schema) == list(PLAN_TABLES)
    assert "BEGIN;" in migration
    assert "COMMIT;" in migration
    assert "IF NOT EXISTS" not in migration.upper()
    assert "ALTER TABLE public." not in migration


def test_plan_columns_match_contract_and_canonical_schema():
    migration = MIGRATION.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    for table_name, expected in EXPECTED_COLUMNS.items():
        migration_body = _table_body(migration, table_name)
        schema_body = _table_body(schema, table_name)
        assert _column_declarations(migration_body) == list(expected)
        if table_name == "plan_template":
            schema_body = schema_body.replace(
                "    is_favorite boolean DEFAULT false NOT NULL,\n",
                "",
            )
        assert _column_declarations(schema_body) == list(expected)
        assert migration_body == schema_body


def test_plan_constraints_and_fk_actions_match_canonical_schema():
    migration = MIGRATION.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    assert _plan_constraints(migration) == EXPECTED_CONSTRAINTS
    assert _plan_constraints(schema) == EXPECTED_CONSTRAINTS
    assert _plan_indexes(migration) == _plan_indexes(schema)
    assert {
        match
        for match in re.findall(r"(?im)^CREATE (?:UNIQUE )?INDEX (plan_[a-z_]+)", migration)
    } == EXPECTED_INDEX_NAMES

    assert (
        "ON DELETE CASCADE ON UPDATE CASCADE"
        in _table_body(migration, "plan_prescription_segment")
    )
    assert (
        "ON DELETE RESTRICT ON UPDATE CASCADE"
        in _table_body(migration, "plan_template")
    )
    item_body = _table_body(migration, "plan_item")
    assert "ON DELETE RESTRICT ON UPDATE CASCADE" in item_body
    assert "ON DELETE SET NULL ON UPDATE CASCADE" in item_body


def test_required_and_optional_text_fields_reject_blank_values():
    sources = (
        MIGRATION.read_text(encoding="utf-8"),
        SCHEMA.read_text(encoding="utf-8"),
    )
    checks = {
        "plan_batch": (
            "CHECK (btrim(batch_type) <> '')",
            "CHECK (btrim(created_by) <> '')",
            "CHECK (idempotency_key IS NULL OR btrim(idempotency_key) <> '')",
        ),
        "plan_item": ("CHECK (btrim(item_source) <> '')",),
        "plan_prescription": (
            "CHECK (sport_type IS NULL OR btrim(sport_type) <> '')",
            "CHECK (activity_category IS NULL OR btrim(activity_category) <> '')",
            "CHECK (target_load_source IS NULL OR btrim(target_load_source) <> '')",
        ),
    }

    for source in sources:
        for table_name, expected_checks in checks.items():
            table_body = _table_body(source, table_name)
            for expected_check in expected_checks:
                assert expected_check in table_body


def test_prescription_ownership_and_item_lifecycle_are_declarative():
    migration = MIGRATION.read_text(encoding="utf-8")
    prescription = _table_body(migration, "plan_prescription")
    template = _table_body(migration, "plan_template")
    item = _table_body(migration, "plan_item")

    assert "UNIQUE (plan_prescription_id, owner_kind)" in prescription
    assert "CHECK (owner_kind IN ('template', 'item'))" in prescription
    assert "UNIQUE (plan_prescription_id)" in template
    assert "UNIQUE (plan_prescription_id)" in item
    assert "CHECK (prescription_owner_kind = 'template')" in template
    assert "CHECK (prescription_owner_kind = 'item')" in item
    assert "FOREIGN KEY (plan_prescription_id, prescription_owner_kind)" in template
    assert "FOREIGN KEY (plan_prescription_id, prescription_owner_kind)" in item

    assert "item_state = 'draft'" in item
    assert "AND plan_batch_id IS NOT NULL" in item
    assert "item_state = 'committed'" in item
    assert "AND committed_at IS NOT NULL" in item
    assert "(item_state = 'cancelled' AND cancelled_at IS NOT NULL)" in item
    assert "cancelled_at >= committed_at" in item


def test_segment_repeat_and_target_contract_is_explicit():
    migration = MIGRATION.read_text(encoding="utf-8")
    segment = _table_body(migration, "plan_prescription_segment")

    assert "UNIQUE (plan_prescription_id, segment_order)" in segment
    assert "CHECK (segment_order > 0)" in segment
    assert "CHECK (repeat_count > 0)" in segment
    assert "repeat_group_key IS NOT NULL OR repeat_count = 1" in segment
    assert "zone_min <= zone_max" in segment
    assert "target_value_min <= target_value_max" in segment
    assert "CHECK (zone_min IS NULL OR target_value_min IS NULL)" in segment
    assert "target_metric = 'none'" in segment
    assert "target_metric <> 'none'" in segment
    assert "zone_profile_id" not in segment


def test_category_seeds_are_idempotent_and_do_not_overwrite_edits():
    migration = MIGRATION.read_text(encoding="utf-8")
    seed_match = re.search(
        r"(?ims)INSERT INTO public\.plan_category\s*\((.*?)\)\s*VALUES(.*?)"
        r"ON CONFLICT \(category_key\) DO NOTHING;",
        migration,
    )
    assert seed_match is not None
    assert "color_key" in seed_match.group(1)
    assert "icon_key" in seed_match.group(1)
    seeds = re.findall(
        r"\('([a-z_]+)', '([^']+)', (\d+), NULL, NULL, true\)",
        seed_match.group(2),
    )
    assert seeds == [
        ("endurance", "Endurance", "1"),
        ("intensity", "Intensity", "2"),
        ("strength", "Strength", "3"),
        ("recovery", "Recovery", "4"),
        ("rest", "Rest", "5"),
        ("bike_park", "Bike Park", "6"),
        ("event", "Event", "7"),
        ("travel", "Travel", "8"),
        ("rehabilitation", "Rehabilitation", "9"),
    ]


def test_plan_schema_is_isolated_from_zones_overrides_and_actual_etl():
    migration = MIGRATION.read_text(encoding="utf-8").lower()
    assert "zone_profile_id" not in migration
    assert "training_zone_profile" not in migration
    assert "training_zone_band" not in migration
    assert "jsonb" not in migration
    assert "activity_interpretation" not in migration
    assert "strava_activities" not in migration
    assert "daily_training" not in migration
    assert "weekly_training" not in migration
    assert "daily_fitness_fatigue" not in migration

    actual_etl_files = (
        "daily_builder.py",
        "weekly_builder.py",
        "fitness_fatigue_builder.py",
        "load_rules.py",
        "db_writer.py",
    )
    plan_table_pattern = re.compile(
        r"\b(?:plan_category|plan_prescription|plan_prescription_segment|"
        r"plan_template|plan_batch|plan_item)\b",
        re.IGNORECASE,
    )
    for name in actual_etl_files:
        source = (ROOT / "src" / name).read_text(encoding="utf-8")
        assert plan_table_pattern.search(source) is None, name
