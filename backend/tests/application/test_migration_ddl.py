from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "backend" / "migrations" / "versions" / "0001_initial.py"
MIGRATION_M2 = ROOT / "backend" / "migrations" / "versions" / "0002_m2_auth_source.py"


def test_initial_migration_is_explicit_ddl() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "create_all" not in text
    assert "drop_all" not in text
    assert "CREATE TABLE seasons" in text
    assert "ex_seasons_no_overlap" in text
    assert "CREATE EXTENSION IF NOT EXISTS btree_gist" in text
    assert "uq_rounds_session_nonterminal" in text


def test_m2_migration_is_explicit_ddl() -> None:
    text = MIGRATION_M2.read_text(encoding="utf-8")
    assert "create_all" not in text
    assert "CREATE TABLE overlay_tickets" in text
    assert "CREATE TABLE google_credentials" in text
    assert "CREATE TABLE idempotency_keys" in text

