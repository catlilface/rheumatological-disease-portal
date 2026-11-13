from pathlib import Path
import re

from sqlalchemy import CheckConstraint, Date, DateTime, UniqueConstraint
from sqlalchemy.dialects import postgresql


REFERENCE = Path(__file__).parent / "fixtures" / "required_schema.sql"


def reference_tables():
    sql = REFERENCE.read_text(encoding="utf-8")
    return dict(re.findall(r"CREATE TABLE\s+(\w+)\s*\((.*?)\n\);", sql, re.S))


def normalize(text):
    return re.sub(r"\s+", "", str(text)).lower()


def test_models_preserve_required_columns_types_defaults_and_constraints():
    from app.database.base import Base
    import app.database.models  # Registers all tables in metadata.

    expected = reference_tables()
    assert set(Base.metadata.tables) == set(expected)
    total_columns = 0
    for table_name, body in expected.items():
        table = Base.metadata.tables[table_name]
        fields = [re.match(r"\s+(\w+)\s+(\w+(?:\(\d+\))?(?:\[\])?)(.*)", line)
                  for line in body.splitlines()]
        fields = [m.groups() for m in fields if m and m.group(1) != "UNIQUE"]
        total_columns += len(fields)
        assert set(table.columns.keys()) == {name for name, _, _ in fields}, table_name
        for name, sql_type, definition in fields:
            column = table.columns[name]
            expected_type = {"bigserial": "BIGINT", "timestamptz": "TIMESTAMP WITH TIME ZONE"}.get(sql_type, sql_type)
            assert normalize(column.type.compile(dialect=postgresql.dialect())) == normalize(expected_type), (table_name, name)
            assert column.nullable == ("NOT NULL" not in definition and "PRIMARY KEY" not in definition), (table_name, name)
            assert column.primary_key == ("PRIMARY KEY" in definition), (table_name, name)
            default = re.search(r"DEFAULT\s+(gen_random_uuid\(\)|now\(\)|'[^']*'|false|true|\d+)", definition)
            if default:
                assert column.server_default is not None, (table_name, name)
                assert normalize(column.server_default.arg) == normalize(default.group(1)), (table_name, name)
            else:
                assert column.server_default is None, (table_name, name)
            reference = re.search(r"REFERENCES\s+(\w+)\((\w+)\)", definition)
            if reference:
                assert len(column.foreign_keys) == 1
                foreign_key = next(iter(column.foreign_keys))
                assert foreign_key.target_fullname == ".".join(reference.groups())
                assert foreign_key.ondelete == ("CASCADE" if "ON DELETE CASCADE" in definition else None)
            else:
                assert not column.foreign_keys, (table_name, name)
            check = re.search(r"CHECK\s*(\([^)]*\))", definition)
            if check:
                checks = [normalize(c.sqltext).strip("()") for c in table.constraints if isinstance(c, CheckConstraint)]
                assert normalize(check.group(1)).strip("()") in checks, (table_name, name)
        expected_unique = {tuple(c.strip() for c in match.split(",")) for match in re.findall(r"UNIQUE\s*\(([^)]*)\)", body)}
        expected_unique.update((name,) for name, _, definition in fields if "UNIQUE" in definition)
        actual_unique = {tuple(c.name for c in constraint.columns) for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
        assert actual_unique == expected_unique, table_name
    assert total_columns == 110


def test_model_enums_match_all_required_values():
    from app.database.base import Base
    import app.database.models

    sql = REFERENCE.read_text(encoding="utf-8")
    expected = {name: re.findall(r"'([^']*)'", values) for name, values in re.findall(r"CREATE TYPE\s+(\w+)\s+AS ENUM\s*\(([^)]*)\)", sql)}
    actual = {c.type.name: c.type.enums for table in Base.metadata.tables.values() for c in table.columns if isinstance(c.type, postgresql.ENUM)}
    assert len(actual) == 9
    assert actual == expected


def test_required_indexes_include_descending_diary_date_without_duplicate_token_index():
    from app.database.base import Base
    import app.database.models

    expected = {
        "symptom_entries": ["user_id", "entry_date DESC"],
        "medication_intake_log": ["user_id", "scheduled_date"],
        "lab_results": ["user_id", "lab_date"],
        "access_audit": ["patient_id", "created_at"],
    }
    for table_name, expressions in expected.items():
        table = Base.metadata.tables[table_name]
        actual = [[str(expr.compile(dialect=postgresql.dialect())).replace(table_name + ".", "") for expr in index.expressions] for index in table.indexes]
        assert expressions in actual, table_name
    assert not Base.metadata.tables["screening_sessions"].indexes


def test_schema_has_no_day_level_birth_date():
    from app.database.base import Base
    import app.database.models

    for table in Base.metadata.tables.values():
        for column in table.columns:
            assert not (re.search(r"birth|dob", column.name, re.I) and isinstance(column.type, (Date, DateTime))), (table.name, column.name)
