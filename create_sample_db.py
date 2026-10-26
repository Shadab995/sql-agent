"""Create a small sample SQLite database (an online shop) to try the SQL Agent on.

Usage:
    python create_sample_db.py            # creates shop.db
    python create_sample_db.py my.db      # custom file name
"""

import random
import sqlite3
import sys
from datetime import date, timedelta

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "shop.db"
random.seed(42)  # same data every time

CUSTOMERS = [
    ("Amina", "Benali", "Morocco", "Casablanca"),
    ("Lucas", "Martin", "France", "Paris"),
    ("Sofia", "Rossi", "Italy", "Milan"),
    ("Youssef", "El Idrissi", "Morocco", "Rabat"),
    ("Emma", "Dubois", "France", "Lyon"),
    ("Liam", "Smith", "United Kingdom", "London"),
    ("Mia", "Müller", "Germany", "Berlin"),
    ("Omar", "Haddad", "Egypt", "Cairo"),
    ("Chloé", "Bernard", "France", "Marseille"),
    ("Noah", "Johnson", "United States", "New York"),
    ("Sara", "Lopez", "Spain", "Madrid"),
    ("Adam", "Kowalski", "Poland", "Warsaw"),
    ("Lina", "Mansour", "Morocco", "Marrakech"),
    ("Hugo", "Lefebvre", "France", "Toulouse"),
    ("Olivia", "Brown", "United States", "Chicago"),
]

PRODUCTS = [
    ("Wireless Mouse", "Electronics", 24.99),
    ("Mechanical Keyboard", "Electronics", 89.00),
    ("27\" 4K Monitor", "Electronics", 329.00),
    ("USB-C Hub", "Electronics", 39.50),
    ("Noise-Cancelling Headphones", "Electronics", 199.00),
    ("Standing Desk", "Furniture", 449.00),
    ("Ergonomic Chair", "Furniture", 279.00),
    ("Desk Lamp", "Furniture", 35.00),
    ("Python Crash Course (book)", "Books", 32.00),
    ("Designing Data-Intensive Applications (book)", "Books", 45.00),
    ("Clean Code (book)", "Books", 38.00),
    ("Coffee Mug", "Accessories", 12.00),
    ("Laptop Backpack", "Accessories", 59.00),
    ("Notebook Pack", "Accessories", 9.50),
]

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    country     TEXT NOT NULL,
    city        TEXT NOT NULL,
    signup_date DATE NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    price      REAL NOT NULL
);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date  DATE NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('delivered', 'shipped', 'pending', 'cancelled'))
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL NOT NULL
);
"""


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    start = date(2025, 1, 1)
    for i, (first, last, country, city) in enumerate(CUSTOMERS, start=1):
        signup = start + timedelta(days=random.randint(0, 200))
        cur.execute("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", (i, first, last, country, city, signup.isoformat()))

    for i, (name, category, price) in enumerate(PRODUCTS, start=1):
        cur.execute("INSERT INTO products VALUES (?, ?, ?, ?)", (i, name, category, price))

    item_id = 1
    statuses = ["delivered"] * 7 + ["shipped"] * 2 + ["pending", "cancelled"]
    for order_id in range(1, 121):
        customer_id = random.randint(1, len(CUSTOMERS))
        order_date = start + timedelta(days=random.randint(30, 640))
        cur.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            (order_id, customer_id, order_date.isoformat(), random.choice(statuses)),
        )
        for product_id in random.sample(range(1, len(PRODUCTS) + 1), k=random.randint(1, 4)):
            price = PRODUCTS[product_id - 1][2]
            cur.execute(
                "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)",
                (item_id, order_id, product_id, random.randint(1, 3), price),
            )
            item_id += 1

    conn.commit()
    conn.close()
    print(f"✅ Created {DB_PATH}: {len(CUSTOMERS)} customers, {len(PRODUCTS)} products, 120 orders, {item_id - 1} order items")


if __name__ == "__main__":
    main()
