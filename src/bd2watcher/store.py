import sqlite3
from datetime import datetime
from decimal import Decimal

from bd2watcher.models import Listing

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_checks (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    listing_count INTEGER NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS listings (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    series TEXT NOT NULL,
    kind TEXT NOT NULL,
    price TEXT,
    currency TEXT NOT NULL,
    stock_state TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);
"""


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def save_listings(self, listings: list[Listing], seen_at: datetime) -> None:
        with self.db:
            self.db.executemany(
                """
                INSERT INTO listings
                    (source, external_id, title, url, series, kind, price, currency,
                     stock_state, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, external_id) DO UPDATE SET
                    title = excluded.title, url = excluded.url, series = excluded.series,
                    kind = excluded.kind, price = excluded.price, currency = excluded.currency,
                    stock_state = excluded.stock_state, last_seen = excluded.last_seen
                """,
                [
                    (
                        l.source, l.external_id, l.title, l.url, l.series, l.kind,
                        None if l.price is None else str(l.price), l.currency,
                        l.stock_state, seen_at.isoformat(), seen_at.isoformat(),
                    )
                    for l in listings
                ],
            )

    def record_check(self, source: str, checked_at: datetime, ok: bool,
                     listing_count: int, error: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO source_checks (source, checked_at, ok, listing_count, error)"
                " VALUES (?, ?, ?, ?, ?)",
                (source, checked_at.isoformat(), int(ok), listing_count, error),
            )

    def listings(self, source: str) -> list[Listing]:
        rows = self.db.execute(
            "SELECT source, external_id, title, url, series, kind, price, currency, stock_state"
            " FROM listings WHERE source = ? ORDER BY title",
            (source,),
        )
        return [
            Listing(
                source=r[0], external_id=r[1], title=r[2], url=r[3], series=r[4], kind=r[5],
                price=None if r[6] is None else Decimal(r[6]), currency=r[7], stock_state=r[8],
            )
            for r in rows
        ]
