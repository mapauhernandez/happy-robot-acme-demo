"""Utility helpers for managing the sample loads SQLite database."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Mapping

DB_PATH = Path(__file__).resolve().parent / "loads.db"

# Table used to persist negotiation insights that will later power
# a lightweight dashboard. Values are stored as TEXT to keep the
# ingestion flexible (the API currently receives numeric fields as
# strings and we want to preserve the original payload).
NEGOTIATION_TABLE_NAME = "negotiation_events"
NEGOTIATION_COLUMNS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "load_accepted TEXT NOT NULL",
    "posted_price TEXT NOT NULL",
    "final_price TEXT NOT NULL",
    "total_negotiations TEXT NOT NULL",
    "call_sentiment TEXT NOT NULL",
    "commodity TEXT NOT NULL",
    "created_at TEXT NOT NULL"
)


STATE_LOAD_DETAILS: List[tuple[str, str, str, str, str]] = [
    ("AL", "Birmingham", "Charlotte, NC", "Flatbed", "Steel Beams"),
    ("AK", "Anchorage", "Seattle, WA", "Reefer", "Seafood"),
    ("AZ", "Phoenix", "Denver, CO", "Dry Van", "Consumer Goods"),
    ("AR", "Little Rock", "Memphis, TN", "Dry Van", "Paper Products"),
    ("CA", "Los Angeles", "Portland, OR", "Dry Van", "Apparel"),
    ("CO", "Denver", "Salt Lake City, UT", "Reefer", "Fresh Produce"),
    ("CT", "Hartford", "Albany, NY", "Dry Van", "Medical Supplies"),
    ("DE", "Wilmington", "Baltimore, MD", "Dry Van", "Packaged Foods"),
    ("FL", "Miami", "Atlanta, GA", "Reefer", "Frozen Foods"),
    ("GA", "Savannah", "Birmingham, AL", "Flatbed", "Lumber"),
    ("HI", "Honolulu", "Los Angeles, CA", "Reefer", "Processed Foods"),
    ("ID", "Boise", "Spokane, WA", "Dry Van", "Paper Products"),
    ("IL", "Chicago", "Detroit, MI", "Flatbed", "Machinery"),
    ("IN", "Indianapolis", "Columbus, OH", "Dry Van", "Automotive Parts"),
    ("IA", "Des Moines", "Minneapolis, MN", "Dry Van", "Agricultural Supplies"),
    ("KS", "Wichita", "Oklahoma City, OK", "Flatbed", "Construction Materials"),
    ("KY", "Louisville", "St. Louis, MO", "Reefer", "Beverages"),
    ("LA", "New Orleans", "Houston, TX", "Flatbed", "Petrochemical Equipment"),
    ("ME", "Portland", "Boston, MA", "Dry Van", "Seafood"),
    ("MD", "Baltimore", "Newark, NJ", "Dry Van", "Consumer Packaged Goods"),
    ("MA", "Boston", "Manchester, NH", "Dry Van", "Pharmaceuticals"),
    ("MI", "Detroit", "Cleveland, OH", "Flatbed", "Steel Coils"),
    ("MN", "Minneapolis", "Milwaukee, WI", "Reefer", "Processed Foods"),
    ("MS", "Jackson", "Baton Rouge, LA", "Dry Van", "Paper Products"),
    ("MO", "St. Louis", "Kansas City, KS", "Flatbed", "Industrial Equipment"),
    ("MT", "Billings", "Fargo, ND", "Flatbed", "Oilfield Supplies"),
    ("NE", "Omaha", "Sioux Falls, SD", "Dry Van", "Food Ingredients"),
    ("NV", "Las Vegas", "Phoenix, AZ", "Dry Van", "Electronics"),
    ("NH", "Manchester", "Hartford, CT", "Dry Van", "Medical Devices"),
    ("NJ", "Newark", "Buffalo, NY", "Dry Van", "Packaged Foods"),
    ("NM", "Albuquerque", "Tulsa, OK", "Flatbed", "Construction Materials"),
    ("NY", "Albany", "Pittsburgh, PA", "Dry Van", "Paper Goods"),
    ("NC", "Charlotte", "Columbia, SC", "Dry Van", "Textiles"),
    ("ND", "Fargo", "Billings, MT", "Flatbed", "Agricultural Machinery"),
    ("OH", "Columbus", "Nashville, TN", "Power Only", "Empty Trailers"),
    ("OK", "Oklahoma City", "Dallas, TX", "Flatbed", "Oilfield Equipment"),
    ("OR", "Portland", "Boise, ID", "Dry Van", "Wood Products"),
    ("PA", "Philadelphia", "Richmond, VA", "Dry Van", "Retail Goods"),
    ("RI", "Providence", "Hartford, CT", "Dry Van", "Office Supplies"),
    ("SC", "Columbia", "Savannah, GA", "Dry Van", "Automotive Components"),
    ("SD", "Sioux Falls", "Omaha, NE", "Reefer", "Dairy Products"),
    ("TN", "Nashville", "Indianapolis, IN", "Dry Van", "Music Equipment"),
    ("TX", "Dallas", "Little Rock, AR", "Dry Van", "Consumer Goods"),
    ("UT", "Salt Lake City", "Reno, NV", "Flatbed", "Mining Equipment"),
    ("VT", "Burlington", "Albany, NY", "Dry Van", "Maple Products"),
    ("VA", "Richmond", "Raleigh, NC", "Dry Van", "Furniture"),
    ("WA", "Seattle", "Boise, ID", "Dry Van", "Paper Products"),
    ("WV", "Charleston", "Lexington, KY", "Dry Van", "Chemicals"),
    ("WI", "Milwaukee", "Chicago, IL", "Reefer", "Cheese"),
    ("WY", "Cheyenne", "Denver, CO", "Flatbed", "Mining Supplies"),
]


DIMENSIONS_BY_EQUIPMENT = {
    "Dry Van": "53ft dry van",
    "Reefer": "53ft refrigerated trailer",
    "Flatbed": "48ft flatbed",
    "Power Only": "Sleeper tractor",
}

EQUIPMENT_NOTES = {
    "Dry Van": "Standard dock pickup with palletized freight.",
    "Reefer": "Maintain temperature setpoint throughout transit.",
    "Flatbed": "Straps and edge protectors provided with load.",
    "Power Only": "Hook and go — trailer ready at shipper.",
}


def _build_seed_loads() -> List[Mapping[str, object]]:
    """Generate one example load per U.S. state."""

    now = datetime.utcnow()
    # Schedule the first pickup for tomorrow at 8:00 AM UTC so the demo data
    # always appears in the near future.
    base_pickup = (now + timedelta(days=1)).replace(
        hour=8, minute=0, second=0, microsecond=0
    )
    loads: List[Mapping[str, object]] = []

    for index, (state, city, destination, equipment, commodity) in enumerate(
        STATE_LOAD_DETAILS, start=1
    ):
        pickup_dt = base_pickup + timedelta(days=index)
        delivery_dt = pickup_dt + timedelta(days=2, hours=(index % 5) * 3)
        rate = round(1700 + 65 * index, 2)
        weight = 26000 + 450 * index
        if equipment == "Power Only":
            weight = 18000
        num_pieces = 10 + (index % 12)
        miles = 300 + 22 * index

        note = f"{EQUIPMENT_NOTES.get(equipment, 'No special handling required.')} Departing {city}."
        if index % 7 == 0:
            note += " Team transit recommended for on-time delivery."

        loads.append(
            {
                "load_id": f"L-{2000 + index:04d}",
                "origin": f"{city}, {state}",
                "destination": destination,
                "pickup_datetime": pickup_dt.isoformat(timespec="minutes"),
                "delivery_datetime": delivery_dt.isoformat(timespec="minutes"),
                "equipment_type": equipment,
                "loadboard_rate": float(rate),
                "notes": note,
                "weight": weight,
                "commodity_type": commodity,
                "num_of_pieces": num_pieces,
                "miles": miles,
                "dimensions": DIMENSIONS_BY_EQUIPMENT.get(equipment, "53ft trailer"),
            }
        )

    return loads


SEED_LOADS = tuple(_build_seed_loads())


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row access as dictionaries."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database() -> None:
    """Create the loads table and seed it with demo data when empty."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS loads (
                load_id TEXT PRIMARY KEY,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                pickup_datetime TEXT NOT NULL,
                delivery_datetime TEXT NOT NULL,
                equipment_type TEXT NOT NULL,
                loadboard_rate REAL NOT NULL,
                notes TEXT,
                weight INTEGER NOT NULL,
                commodity_type TEXT NOT NULL,
                num_of_pieces INTEGER NOT NULL,
                miles INTEGER NOT NULL,
                dimensions TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {NEGOTIATION_TABLE_NAME} (
                {', '.join(NEGOTIATION_COLUMNS)}
            )
            """
        )
        conn.commit()

        existing_ids = {
            row["load_id"] for row in conn.execute("SELECT load_id FROM loads").fetchall()
        }
        seed_ids = {load["load_id"] for load in SEED_LOADS}
        if existing_ids == seed_ids:
            return

        if existing_ids:
            conn.execute("DELETE FROM loads")

        insert_query = """
            INSERT INTO loads (
                load_id,
                origin,
                destination,
                pickup_datetime,
                delivery_datetime,
                equipment_type,
                loadboard_rate,
                notes,
                weight,
                commodity_type,
                num_of_pieces,
                miles,
                dimensions
            ) VALUES (
                :load_id,
                :origin,
                :destination,
                :pickup_datetime,
                :delivery_datetime,
                :equipment_type,
                :loadboard_rate,
                :notes,
                :weight,
                :commodity_type,
                :num_of_pieces,
                :miles,
                :dimensions
            )
        """
        conn.executemany(insert_query, SEED_LOADS)
        conn.commit()


def record_negotiation_event(payload: Mapping[str, str]) -> None:
    """Persist a negotiation event so it can be surfaced in dashboards."""

    required_keys = {
        "load_accepted",
        "posted_price",
        "final_price",
        "total_negotiations",
        "call_sentiment",
        "commodity",
        "created_at",
    }

    missing_keys = required_keys.difference(payload)
    if missing_keys:
        missing_str = ", ".join(sorted(missing_keys))
        raise ValueError(f"Missing keys for negotiation event: {missing_str}")

    with get_connection() as conn:
        conn.execute(
            f"""
            INSERT INTO {NEGOTIATION_TABLE_NAME} (
                load_accepted,
                posted_price,
                final_price,
                total_negotiations,
                call_sentiment,
                commodity,
                created_at
            ) VALUES (
                :load_accepted,
                :posted_price,
                :final_price,
                :total_negotiations,
                :call_sentiment,
                :commodity,
                :created_at
            )
            """,
            payload,
        )
        conn.commit()


def fetch_negotiation_events() -> List[sqlite3.Row]:
    """Return every recorded negotiation event ordered by creation time."""

    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM {NEGOTIATION_TABLE_NAME} ORDER BY created_at ASC"
        ).fetchall()
    return rows


def fetch_all_loads() -> List[sqlite3.Row]:
    """Return every load from the database."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM loads").fetchall()
    return rows
