from data.seed_database import create_database
from src.database.sqlite import execute_sql, schema_description


def test_seed_database_has_required_tables(tmp_path):
    path = create_database(tmp_path / "business.sqlite3")
    schema = schema_description(path)
    for name in ("customers", "orders", "products", "transactions", "support_tickets"):
        assert f"CREATE TABLE {name}" in schema
    assert execute_sql("SELECT COUNT(*) AS n FROM orders", path)["rows"][0]["n"] > 0


def test_seed_is_non_destructive_without_force(tmp_path):
    path = create_database(tmp_path / "business.sqlite3")
    original = path.read_bytes()
    create_database(path)
    assert path.read_bytes() == original
