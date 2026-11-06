"""Create deterministic, explicitly synthetic business records for demos."""
from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import settings

NAMES = ["Avery Chen", "Jordan Patel", "Morgan Rivera", "Taylor Kim", "Casey Morgan", "Riley Singh", "Quinn Brooks", "Jamie Shah", "Alex Turner", "Samira Khan", "Drew Wilson", "Cameron Lee"]
REGIONS = ["North America", "Europe", "Asia Pacific"]
SEGMENTS = ["Small Business", "Mid-Market", "Enterprise"]
PRODUCTS = [("Atlas Analytics", "Software", 149.0), ("Orbit CRM", "Software", 89.0), ("Pulse Support", "Service", 59.0), ("Beacon Insights", "Software", 219.0)]


def create_database(path: str | Path | None = None, force: bool = False) -> Path:
    """Build the small deterministic sample database and return its path."""
    db_path = Path(path) if path else settings.resolve(settings.sqlite_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and not force:
        return db_path
    if db_path.exists() and force:
        db_path.unlink()
    rng = random.Random(2026)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript((Path(__file__).parent.parent / "src/database/schema.sql").read_text())
        today = date(2026, 11, 1)
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", [
            (i + 1, name, SEGMENTS[i % 3], REGIONS[i % 3], (today - timedelta(days=400 + i * 73)).isoformat(), int(i % 6 != 0))
            for i, name in enumerate(NAMES)
        ])
        conn.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?)", [
            (i + 1, name, cat, price, (today - timedelta(days=120 + i * 40)).isoformat())
            for i, (name, cat, price) in enumerate(PRODUCTS)
        ])
        orders, transactions, tickets = [], [], []
        for i in range(1, 61):
            customer = (i - 1) % len(NAMES) + 1
            product = PRODUCTS[(i - 1) % len(PRODUCTS)]
            # Synthetic demand softens during Q3 to support causal-analysis demos.
            month_offset = (i * 7) % 12
            order_day = date(2026, 1, 1) + timedelta(days=month_offset * 25 + (i % 20))
            amount = round(product[2] * (1 + (i % 3) * .15), 2)
            status = "completed" if i % 11 else "cancelled"
            orders.append((i, customer, order_day.isoformat(), status, amount))
            transactions.append((i, i, order_day.isoformat(), "charge", amount, "settled" if status == "completed" else "voided"))
            if i % 4 == 0:
                created = order_day + timedelta(days=i % 10)
                tickets.append((len(tickets) + 1, customer, created.isoformat(), ["billing", "product issue", "onboarding"][i % 3], ["low", "medium", "high"][i % 3], "open" if i % 8 == 0 else "closed", 2 + i % 4))
        conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)
        conn.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)", transactions)
        conn.executemany("INSERT INTO support_tickets VALUES (?, ?, ?, ?, ?, ?, ?)", tickets)
        conn.commit()
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true", help="Replace an existing database at the output path")
    args = parser.parse_args()
    print(f"Synthetic sample database ready: {create_database(args.output, force=args.force)}")
