import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "sql" / "Applied" / "app_preference_v1.sql"
SCHEMA = ROOT / "sql" / "training_postgress_db_schema.sql"


def _table_body(sql, table_name):
    match = re.search(
        rf"(?ims)^CREATE TABLE public\.{re.escape(table_name)}\s*\((.*?)^\);",
        sql,
    )
    assert match is not None, f"missing definition for {table_name}"
    return match.group(1)


def test_app_preference_migration_is_additive_and_seeds_plan_default():
    sql = MIGRATION.read_text(encoding="utf-8")
    body = _table_body(sql, "app_preference")

    assert "BEGIN;" in sql
    assert "COMMIT;" in sql
    assert "preference_namespace text NOT NULL" in body
    assert "preference_value jsonb NOT NULL" in body
    assert "updated_at timestamptz DEFAULT now() NOT NULL" in body
    assert "PRIMARY KEY (preference_namespace)" in body
    assert "btrim(preference_namespace) <> ''" in body
    assert "jsonb_typeof(preference_value) = 'object'" in body
    assert (
        "VALUES ('plan_view', '{\"hide_past_planned\": true}'::jsonb)"
        in sql
    )
    assert "ON CONFLICT (preference_namespace) DO NOTHING" in sql
    assert "Manual application only" in sql
    assert "Read-only verification queries" in sql
    assert "-- DROP TABLE public.app_preference;" in sql
    assert not re.search(r"(?im)^\s*(?:UPDATE|DELETE)\s+public\.", sql)
    assert not re.search(
        r"public\.(?:plan_item|plan_template|strava_activities|daily_|weekly_|load)",
        sql,
    )


def test_authoritative_schema_contains_generic_app_preference_contract():
    sql = SCHEMA.read_text(encoding="utf-8")
    body = _table_body(sql, "app_preference")

    assert "preference_namespace text NOT NULL" in body
    assert "preference_value jsonb NOT NULL" in body
    assert "updated_at timestamptz DEFAULT now() NOT NULL" in body
    assert "app_preference_pkey" in body
    assert "app_preference_namespace_check" in body
    assert "app_preference_value_object_check" in body
