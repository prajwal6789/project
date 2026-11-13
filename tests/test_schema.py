import sqlite3
from pathlib import Path


def test_schema_loads_into_sqlite():
    schema = Path("docs/schema.sql").read_text(encoding="utf-8")
    connection = sqlite3.connect(":memory:")
    connection.executescript(schema)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"Customer", "Product", "OrderHeader", "OrderLine", "SegmentMembership", "ActionOutcome"} <= tables
