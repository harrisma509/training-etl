import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "sql" / "Applied" / "plan_template_quick_picks_v1.sql"
SCHEMA = ROOT / "sql" / "training_postgress_db_schema.sql"


def test_quick_pick_migration_is_additive_and_transactional():
    migration = MIGRATION.read_text(encoding="utf-8")
    assert migration.startswith("-- Plan Template Quick Picks V1.")
    assert "BEGIN;" in migration
    assert "COMMIT;" in migration
    assert "ADD COLUMN IF NOT EXISTS is_favorite boolean" in migration
    assert "ALTER COLUMN is_favorite SET DEFAULT false" in migration
    assert "ALTER COLUMN is_favorite SET NOT NULL" in migration
    assert "CREATE INDEX" not in migration.upper()
    assert "DROP " not in migration.upper()


def test_quick_pick_seed_uses_normalized_name_and_category_key():
    migration = MIGRATION.read_text(encoding="utf-8").lower()
    for name, category in (
        ("prehab", "rehabilitation"),
        ("core strength", "strength"),
        ("recovery ride", "recovery"),
        ("rest day", "rest"),
        ("z2 endurance ride", "endurance"),
        ("dog walk", "recovery"),
    ):
        assert f"lower(btrim(pt.template_name)) = '{name}'" in migration
        assert f"pc.category_key = '{category}'" in migration
    assert "pt.is_active = true" in migration
    assert "having count(*) > 1" in migration
    assert "bike park day" not in migration


def test_canonical_schema_contains_non_null_quick_pick_column():
    schema = SCHEMA.read_text(encoding="utf-8")
    table = re.search(
        r"(?ims)^CREATE TABLE public\.plan_template\s*\((.*?)^\);",
        schema,
    )
    assert table is not None
    assert "is_favorite boolean DEFAULT false NOT NULL" in table.group(1)


def test_migration_does_not_touch_non_plan_or_actual_tables():
    migration = MIGRATION.read_text(encoding="utf-8").lower()
    for forbidden in (
        "plan_item",
        "plan_batch",
        "plan_prescription",
        "strava_activities",
        "daily_training",
        "weekly_training",
        "daily_fitness_fatigue",
        "checkin",
    ):
        assert forbidden not in migration
