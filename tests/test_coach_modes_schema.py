from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "sql" / "ai_coach_modes_v1_slice_1.sql"
SCHEMA = ROOT / "sql" / "training_postgress_db_schema.sql"


def test_coach_modes_migration_contract_is_additive_and_reviewable():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ADD COLUMN current_mode text DEFAULT 'training' NOT NULL" in sql
    assert "ADD COLUMN coach_mode text DEFAULT 'training' NOT NULL" in sql
    assert "current_mode IN ('training', 'conversational')" in sql
    assert "coach_mode IN ('training', 'conversational')" in sql
    assert "information_schema.columns" in sql
    assert "pg_constraint" in sql
    assert "DROP COLUMN coach_mode" in sql
    assert "DROP COLUMN current_mode" in sql


def test_authoritative_schema_contains_bounded_mode_columns():
    sql = SCHEMA.read_text(encoding="utf-8")
    assert "current_mode text DEFAULT 'training'::text NOT NULL" in sql
    assert "coach_mode text DEFAULT 'training'::text NOT NULL" in sql
    assert "coach_session_current_mode_check" in sql
    assert "coach_turn_coach_mode_check" in sql