"""
Generates orders.db - synthetic sales data for the Data Analyst Agent.

Deterministic (fixed seed) so the same anomaly is there every time this
is run. The anomaly: LATAM's Electronics revenue drops hard from Q1 to Q2
2026 while every other region/category grows normally - findable only by
drilling overall -> region -> category, not from a single query. Q3 2026
is left entirely empty (it hasn't happened yet) for the no-data case.

Run:
    python seed_orders_db.py
"""

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DB_PATH = Path(__file__).resolve().parent / "orders.db"

PRODUCTS = {
    "Electronics": [("Laptop", 1200), ("Headphones", 150), ("Monitor", 300)],
    "Furniture": [("Desk", 400), ("Chair", 200), ("Bookshelf", 150)],
    "Apparel": [("Jacket", 120), ("Shoes", 90), ("Backpack", 70)],
    "Software": [
        ("ProjectSuite License", 500),
        ("SecurityShield License", 350),
        ("CloudSync License", 250),
    ],
}

QUARTERS = {
    "Q1": (date(2026, 1, 1), date(2026, 3, 31)),
    "Q2": (date(2026, 4, 1), date(2026, 6, 30)),
    # Q3 2026 deliberately has no bucket below - no rows will exist for it.
}

# (region, category) -> {quarter: target_revenue}. LATAM/Electronics is the
# planted anomaly: everything else grows ~10-13% quarter over quarter,
# LATAM Electronics drops ~60%.
TARGETS = {
    ("North America", "Electronics"): {"Q1": 45000, "Q2": 50000},
    ("North America", "Furniture"): {"Q1": 20000, "Q2": 22000},
    ("North America", "Apparel"): {"Q1": 15000, "Q2": 17000},
    ("North America", "Software"): {"Q1": 30000, "Q2": 34000},
    ("Europe", "Electronics"): {"Q1": 40000, "Q2": 44000},
    ("Europe", "Furniture"): {"Q1": 18000, "Q2": 20000},
    ("Europe", "Apparel"): {"Q1": 14000, "Q2": 15500},
    ("Europe", "Software"): {"Q1": 28000, "Q2": 31000},
    ("APAC", "Electronics"): {"Q1": 35000, "Q2": 39000},
    ("APAC", "Furniture"): {"Q1": 16000, "Q2": 18000},
    ("APAC", "Apparel"): {"Q1": 12000, "Q2": 13500},
    ("APAC", "Software"): {"Q1": 25000, "Q2": 28000},
    ("LATAM", "Electronics"): {"Q1": 30000, "Q2": 12000},  # the anomaly
    ("LATAM", "Furniture"): {"Q1": 10000, "Q2": 11000},
    ("LATAM", "Apparel"): {"Q1": 8000, "Q2": 9000},
    ("LATAM", "Software"): {"Q1": 15000, "Q2": 17000},
}


def random_date(start: date, end: date) -> str:
    days = (end - start).days
    return (start + timedelta(days=random.randint(0, days))).isoformat()


def generate_bucket_orders(region: str, category: str, quarter: str, target: float) -> list[tuple]:
    start, end = QUARTERS[quarter]
    products = PRODUCTS[category]
    rows = []
    accumulated = 0.0
    while accumulated < target * 0.95:
        product, unit_price = random.choice(products)
        quantity = random.randint(1, 4)
        revenue = round(unit_price * quantity * random.uniform(0.9, 1.1), 2)
        rows.append((random_date(start, end), region, category, product, quantity, revenue))
        accumulated += revenue
    return rows


def main() -> None:
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            region TEXT NOT NULL,
            category TEXT NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            revenue REAL NOT NULL
        )
        """
    )

    all_rows = []
    for (region, category), by_quarter in TARGETS.items():
        for quarter, target in by_quarter.items():
            all_rows.extend(generate_bucket_orders(region, category, quarter, target))

    conn.executemany(
        "INSERT INTO orders (date, region, category, product, quantity, revenue) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        all_rows,
    )
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"Seeded {count} orders into {DB_PATH}")
    conn.close()


if __name__ == "__main__":
    main()
