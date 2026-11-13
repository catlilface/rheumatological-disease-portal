from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config


SERVER = Path(__file__).resolve().parents[1]


def test_upgrade_sql_is_generated_without_database_and_from_any_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output = StringIO()
    command.upgrade(Config(str(SERVER / "alembic.ini"), output_buffer=output), "head", sql=True)
    sql = output.getvalue()
    assert sql.count("CREATE TYPE ") == 9
    assert sql.count("CREATE TABLE ") == 15  # 14 application tables plus alembic_version.
    assert "CREATE TABLE screening_results" in sql
    assert "year_of_birth BETWEEN 1920 AND 2025" in sql
    assert "entry_date DESC" in sql


def test_downgrade_sql_drops_all_tables_before_enum_types():
    output = StringIO()
    command.downgrade(Config(str(SERVER / "alembic.ini"), output_buffer=output), "0001_initial_schema:base", sql=True)
    sql = output.getvalue()
    assert sql.count("DROP TYPE ") == 9
    assert sql.count("DROP TABLE ") == 14
    assert "DELETE FROM alembic_version" in sql
    assert sql.index("DROP TABLE users") < sql.index("DROP TYPE user_role")
