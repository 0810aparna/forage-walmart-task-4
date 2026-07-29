"""
populate_database.py

Reads the three shipping spreadsheets provided by the Walmart shipping
department and inserts their data into shipment_database.db.

Schema (already exists in the .db file):
    product(id INTEGER PK, name TEXT UNIQUE NOT NULL)
    shipment(id INTEGER PK, product_id INTEGER FK -> product.id,
              quantity INTEGER, origin TEXT, destination TEXT)

Data sources:
    shipping_data_0.csv - self-contained. One row = one shipment of one
        product. Columns: origin_warehouse, destination_store, product,
        on_time, product_quantity, driver_identifier.
        `on_time` and `driver_identifier` have no home in the target
        schema, so they are read but intentionally not stored.

    shipping_data_1.csv - one row = one UNIT of one product inside a
        shipment. Columns: shipment_identifier, product, on_time.
        There is no quantity column - the quantity of a given product in
        a shipment is the number of rows that share the same
        (shipment_identifier, product) pair, so those rows have to be
        grouped and counted before they can be inserted.

    shipping_data_2.csv - one row = one shipment's origin/destination.
        Columns: shipment_identifier, origin_warehouse, destination_store,
        driver_identifier. This is the lookup table that spreadsheet 1
        needs to find out where each shipment came from and where it's
        going.

Usage:
    python3 populate_database.py
"""

import csv
import sqlite3
from collections import defaultdict

DB_PATH = "shipment_database.db"
SHEET_0_PATH = "data/shipping_data_0.csv"
SHEET_1_PATH = "data/shipping_data_1.csv"
SHEET_2_PATH = "data/shipping_data_2.csv"


def get_or_create_product_id(cursor, product_name):
    """
    Return the id of `product_name` in the product table, inserting a new
    row first if it doesn't exist yet. This keeps `product` free of
    duplicates even though the same product name shows up in many rows
    (and across both spreadsheets).
    """
    cursor.execute("SELECT id FROM product WHERE name = ?", (product_name,))
    row = cursor.fetchone()
    if row is not None:
        return row[0]

    cursor.execute("INSERT INTO product (name) VALUES (?)", (product_name,))
    return cursor.lastrowid


def insert_shipment(cursor, product_id, quantity, origin, destination):
    cursor.execute(
        """
        INSERT INTO shipment (product_id, quantity, origin, destination)
        VALUES (?, ?, ?, ?)
        """,
        (product_id, quantity, origin, destination),
    )


def process_sheet_0(cursor):
    """
    Spreadsheet 0 is self-contained: every row already has a product,
    quantity, origin and destination, so each row maps directly to one
    shipment row.
    """
    with open(SHEET_0_PATH, newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            product_id = get_or_create_product_id(cursor, row["product"])
            insert_shipment(
                cursor,
                product_id=product_id,
                quantity=int(row["product_quantity"]),
                origin=row["origin_warehouse"],
                destination=row["destination_store"],
            )


def load_shipment_locations(cursor):
    """
    Build a {shipment_identifier: (origin, destination)} lookup from
    spreadsheet 2, so spreadsheet 1's rows (which only carry a
    shipment_identifier) can be matched to an origin/destination.
    """
    locations = {}
    with open(SHEET_2_PATH, newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            locations[row["shipment_identifier"]] = (
                row["origin_warehouse"],
                row["destination_store"],
            )
    return locations


def process_sheet_1(cursor):
    """
    Spreadsheet 1 lists one row per unit of product per shipment, with no
    quantity column. Rows are grouped by (shipment_identifier, product)
    and the group size becomes the quantity for that product within that
    shipment. Origin/destination for each shipment_identifier comes from
    spreadsheet 2 via load_shipment_locations().
    """
    locations = load_shipment_locations(cursor)

    # (shipment_identifier, product) -> quantity
    quantities = defaultdict(int)
    with open(SHEET_1_PATH, newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            key = (row["shipment_identifier"], row["product"])
            quantities[key] += 1

    for (shipment_identifier, product_name), quantity in quantities.items():
        origin, destination = locations[shipment_identifier]
        product_id = get_or_create_product_id(cursor, product_name)
        insert_shipment(
            cursor,
            product_id=product_id,
            quantity=quantity,
            origin=origin,
            destination=destination,
        )


def main():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    try:
        process_sheet_0(cursor)
        process_sheet_1(cursor)
        connection.commit()
        print("Database populated successfully.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()