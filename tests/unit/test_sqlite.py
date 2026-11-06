import pytest

from src.database.sqlite import SQLValidationError, execute_sql, validate_select_sql


def test_accepts_select_and_cte():
    assert validate_select_sql("SELECT 1") == "SELECT 1"
    assert validate_select_sql("WITH t AS (SELECT 1 AS n) SELECT n FROM t").startswith("WITH")


@pytest.mark.parametrize("query", ["DELETE FROM customers", "DROP TABLE customers", "SELECT 1; SELECT 2", "PRAGMA table_info(customers)", "SELECT 1 -- comment"])
def test_rejects_unsafe_sql(query):
    with pytest.raises(SQLValidationError):
        validate_select_sql(query)


def test_execute_sql_limits_rows(tmp_path):
    import sqlite3
    path = tmp_path / "sample.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE example (n INTEGER)")
        conn.executemany("INSERT INTO example VALUES (?)", [(1,), (2,), (3,)])
    result = execute_sql("SELECT n FROM example ORDER BY n", path, max_rows=2)
    assert result["rows"] == [{"n": 1}, {"n": 2}]
    assert result["row_limit"] == 2


def test_zero_row_limit_is_rejected(tmp_path):
    import sqlite3
    path = tmp_path / "sample.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE example (n INTEGER)")
    with pytest.raises(ValueError, match="max_rows"):
        execute_sql("SELECT n FROM example", path, max_rows=0)
