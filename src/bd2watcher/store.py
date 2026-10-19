import sqlite3
from datetime import datetime
from decimal import Decimal

from bd2watcher.models import Alert, Check, Event, Listing

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
    product TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);
-- Events keep a copy of the listing as it was, so alert history doesn't change later.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    at TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    series TEXT NOT NULL,
    listing_kind TEXT NOT NULL,
    price TEXT,
    currency TEXT NOT NULL,
    stock_state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events (id),
    channel TEXT NOT NULL,
    store_label TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT
);
"""


EVENT_COLUMNS = (
    "events.kind, events.at, events.source, events.external_id, events.title, events.url, events.series,"
    " events.listing_kind, events.price, events.currency, events.stock_state"
)


def _event(row) -> Event:
    kind, at, source, external_id, title, url, series, listing_kind, price, currency, stock_state = row
    listing = Listing(
        source=source, external_id=external_id, title=title, url=url, series=series, kind=listing_kind,
        price=None if price is None else Decimal(price), currency=currency, stock_state=stock_state,
    )
    return Event(kind, listing, datetime.fromisoformat(at))


class Store:
    def __init__(self, path: str):
        # The dashboard reads on worker threads; every writer opens its own Store.
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")  # lets the dashboard read while a check writes
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def save_listings(self, listings: list[Listing], seen_at: datetime) -> None:
        with self.db:
            self.db.executemany(
                """
                INSERT INTO listings
                    (source, external_id, title, url, series, kind, price, currency,
                     stock_state, product, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, external_id) DO UPDATE SET
                    title = excluded.title, url = excluded.url, series = excluded.series,
                    kind = excluded.kind, price = excluded.price, currency = excluded.currency,
                    stock_state = excluded.stock_state, product = excluded.product,
                    last_seen = excluded.last_seen
                """,
                [
                    (
                        l.source, l.external_id, l.title, l.url, l.series, l.kind,
                        None if l.price is None else str(l.price), l.currency,
                        l.stock_state, l.product, seen_at.isoformat(), seen_at.isoformat(),
                    )
                    for l in listings
                ],
            )

    def mark_sold_out(self, source: str, external_ids: list[str]) -> None:
        with self.db:
            self.db.executemany(
                "UPDATE listings SET stock_state = 'sold_out' WHERE source = ? AND external_id = ?",
                [(source, i) for i in external_ids],
            )

    def has_successful_check(self, source: str) -> bool:
        row = self.db.execute("SELECT 1 FROM source_checks WHERE source = ? AND ok = 1 LIMIT 1", (source,))
        return row.fetchone() is not None

    def record_event(self, event: Event) -> int:
        l = event.listing
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO events (source, external_id, kind, at, title, url, series, listing_kind,"
                " price, currency, stock_state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (l.source, l.external_id, event.kind, event.at.isoformat(), l.title, l.url, l.series,
                 l.kind, None if l.price is None else str(l.price), l.currency, l.stock_state),
            )
        return cursor.lastrowid

    def undelivered(self, source: str, since: datetime) -> list[tuple[int, str, Event]]:
        """Events whose every send to a channel failed, newer than `since`: (event id, channel, event)."""
        rows = self.db.execute(
            f"SELECT events.id, alerts.channel, {EVENT_COLUMNS} FROM events"
            " JOIN alerts ON alerts.event_id = events.id"
            " WHERE events.source = ? AND events.at >= ?"
            " GROUP BY events.id, alerts.channel HAVING MAX(alerts.ok) = 0 ORDER BY events.id",
            (source, since.isoformat()),
        ).fetchall()
        return [(r[0], r[1], _event(r[2:])) for r in rows]

    def record_alert(self, event_id: int, alert: Alert, ok: bool, error: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO alerts (event_id, channel, store_label, sent_at, ok, error) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, alert.channel, alert.store_label, alert.sent_at.isoformat(), int(ok), error),
            )

    def last_alert_at(self, source: str, external_id: str, kind: str | None = None) -> datetime | None:
        """When this listing last had an alert delivered, optionally only of one event kind."""
        row = self.db.execute(
            "SELECT MAX(alerts.sent_at) FROM alerts JOIN events ON events.id = alerts.event_id"
            " WHERE events.source = ? AND events.external_id = ? AND alerts.ok = 1"
            " AND (? IS NULL OR events.kind = ?)",
            (source, external_id, kind, kind),
        ).fetchone()
        return None if row[0] is None else datetime.fromisoformat(row[0])

    def alerts(self) -> list[Alert]:
        rows = self.db.execute(
            f"SELECT alerts.channel, alerts.store_label, alerts.sent_at, alerts.ok, {EVENT_COLUMNS}"
            " FROM alerts JOIN events ON events.id = alerts.event_id ORDER BY alerts.id"
        ).fetchall()
        return [
            Alert(event.kind, channel, event.listing, store_label, datetime.fromisoformat(sent_at), bool(ok))
            for channel, store_label, sent_at, ok, *rest in rows
            for event in [_event(rest)]
        ]

    def record_check(self, source: str, checked_at: datetime, ok: bool,
                     listing_count: int, error: str | None = None) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO source_checks (source, checked_at, ok, listing_count, error)"
                " VALUES (?, ?, ?, ?, ?)",
                (source, checked_at.isoformat(), int(ok), listing_count, error),
            )

    def last_check(self, source: str) -> "Check | None":
        row = self.db.execute(
            "SELECT checked_at, ok, listing_count, error FROM source_checks"
            " WHERE source = ? ORDER BY id DESC LIMIT 1",
            (source,),
        ).fetchone()
        if row is None:
            return None
        return Check(checked_at=datetime.fromisoformat(row[0]), ok=bool(row[1]),
                     listing_count=row[2], error=row[3])

    def listings(self, source: str | None = None) -> list[Listing]:
        """Listings of one source, or of every source when none is given."""
        rows = self.db.execute(
            "SELECT source, external_id, title, url, series, kind, price, currency, stock_state, product"
            " FROM listings WHERE ? IS NULL OR source = ? ORDER BY title",
            (source, source),
        )
        return [
            Listing(
                source=r[0], external_id=r[1], title=r[2], url=r[3], series=r[4], kind=r[5],
                price=None if r[6] is None else Decimal(r[6]), currency=r[7], stock_state=r[8], product=r[9],
            )
            for r in rows
        ]
