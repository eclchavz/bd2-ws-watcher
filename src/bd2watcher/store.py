import sqlite3
from datetime import date, datetime
from decimal import Decimal

from bd2watcher.models import Alert, Announcement, Check, Event, Listing, PricePoint, SetAlert

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
    stock_state TEXT NOT NULL,
    product TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS price_points (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    price TEXT NOT NULL,
    currency TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS price_points_listing ON price_points (source, external_id, at);
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT PRIMARY KEY,
    usd_rate TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
-- Sources we've told the user are broken; cleared once "recovered" is sent.
CREATE TABLE IF NOT EXISTS broken_sources (source TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS sets (
    source TEXT NOT NULL,
    set_id TEXT NOT NULL,
    title TEXT NOT NULL,
    language TEXT NOT NULL,
    url TEXT NOT NULL,
    series TEXT NOT NULL,
    release_date TEXT,
    first_seen TEXT NOT NULL,
    in_digest_queue INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source, set_id)
);
CREATE TABLE IF NOT EXISTS set_alerts (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    set_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    channel TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    error TEXT
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

# Columns added after a table first shipped: (table, column, definition). Added on startup if missing.
ADDED_COLUMNS = [
    ("listings", "product", "TEXT NOT NULL DEFAULT ''"),
    ("events", "product", "TEXT NOT NULL DEFAULT ''"),
]

EVENT_COLUMNS = (
    "events.kind, events.at, events.source, events.external_id, events.title, events.url, events.series,"
    " events.listing_kind, events.price, events.currency, events.stock_state, events.product"
)


def _event(row) -> Event:
    kind, at, source, external_id, title, url, series, listing_kind, price, currency, stock_state, product = row
    listing = Listing(
        source=source, external_id=external_id, title=title, url=url, series=series, kind=listing_kind,
        price=None if price is None else Decimal(price), currency=currency, stock_state=stock_state,
        product=product,
    )
    return Event(kind, listing, datetime.fromisoformat(at))


SET_COLUMNS = "sets.source, sets.set_id, sets.title, sets.language, sets.url, sets.series, sets.release_date"


def _announcement(row) -> Announcement:
    source, set_id, title, language, url, series, release_date = row
    return Announcement(source, set_id, title, language, url, series,
                        date.fromisoformat(release_date) if release_date else None)


class Store:
    def __init__(self, path: str):
        # The dashboard reads on worker threads (behind a lock); every writer opens its own Store.
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")  # lets the dashboard read while a check writes
        self.db.executescript(SCHEMA)
        for table, column, definition in ADDED_COLUMNS:
            if column not in {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}:
                with self.db:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                " price, currency, stock_state, product) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (l.source, l.external_id, event.kind, event.at.isoformat(), l.title, l.url, l.series,
                 l.kind, None if l.price is None else str(l.price), l.currency, l.stock_state, l.product),
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

    def add_price_point(self, listing: Listing, at: datetime) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO price_points (source, external_id, price, currency, at) VALUES (?, ?, ?, ?, ?)",
                (listing.source, listing.external_id, str(listing.price), listing.currency, at.isoformat()),
            )

    def price_history(self, source: str, external_id: str) -> list[PricePoint]:
        rows = self.db.execute(
            "SELECT price, currency, at FROM price_points WHERE source = ? AND external_id = ? ORDER BY at",
            (source, external_id),
        )
        return [PricePoint(Decimal(p), c, datetime.fromisoformat(at)) for p, c, at in rows]

    def events_of_kind(self, kind: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM events WHERE kind = ?", (kind,)).fetchone()[0]

    def save_rate(self, currency: str, usd_rate, fetched_at: datetime) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO fx_rates (currency, usd_rate, fetched_at) VALUES (?, ?, ?)"
                " ON CONFLICT (currency) DO UPDATE SET usd_rate = excluded.usd_rate, fetched_at = excluded.fetched_at",
                (currency, str(usd_rate), fetched_at.isoformat()),
            )

    def rate_fetched_at(self, currency: str) -> datetime | None:
        row = self.db.execute("SELECT fetched_at FROM fx_rates WHERE currency = ?", (currency,)).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def usd_rate(self, currency: str) -> Decimal | None:
        """How many USD one unit of `currency` is worth, from the last fetch. None if never fetched."""
        if currency == "USD":
            return Decimal("1")
        row = self.db.execute("SELECT usd_rate FROM fx_rates WHERE currency = ?", (currency,)).fetchone()
        return Decimal(row[0]) if row else None

    def save_sets(self, announcements: list[Announcement], seen_at: datetime,
                  queue_for_digest: list[Announcement]) -> None:
        queued = {a.set_id for a in queue_for_digest}
        with self.db:
            self.db.executemany(
                """
                INSERT INTO sets (source, set_id, title, language, url, series, release_date, first_seen,
                                  in_digest_queue)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, set_id) DO UPDATE SET
                    title = excluded.title, url = excluded.url, series = excluded.series,
                    release_date = COALESCE(excluded.release_date, sets.release_date)
                """,
                [
                    (a.source, a.set_id, a.title, a.language, a.url, a.series,
                     a.release_date.isoformat() if a.release_date else None, seen_at.isoformat(),
                     int(a.set_id in queued))
                    for a in announcements
                ],
            )

    def sets(self, source: str | None = None) -> list[Announcement]:
        rows = self.db.execute(
            f"SELECT {SET_COLUMNS} FROM sets WHERE ? IS NULL OR source = ?"
            " ORDER BY release_date IS NULL, release_date DESC, title",
            (source, source),
        )
        return [_announcement(r) for r in rows]

    def digest_queue(self) -> list[Announcement]:
        rows = self.db.execute(f"SELECT {SET_COLUMNS} FROM sets WHERE in_digest_queue = 1 ORDER BY first_seen, title")
        return [_announcement(r) for r in rows]

    def unqueue(self, source: str, set_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE sets SET in_digest_queue = 0 WHERE source = ? AND set_id = ?", (source, set_id))

    def clear_digest_queue(self, announcements: list[Announcement]) -> None:
        with self.db:
            self.db.executemany("UPDATE sets SET in_digest_queue = 0 WHERE source = ? AND set_id = ?",
                                [(a.source, a.set_id) for a in announcements])

    def record_set_alert(self, alert: SetAlert, ok: bool, error: str | None = None) -> None:
        a = alert.announcement
        with self.db:
            self.db.execute(
                "INSERT INTO set_alerts (source, set_id, kind, channel, sent_at, ok, error) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (a.source, a.set_id, alert.event, alert.channel, alert.sent_at.isoformat(), int(ok), error),
            )

    def undelivered_set_alerts(self, source: str, since: datetime) -> list[tuple[Announcement, str, str]]:
        """(announcement, event kind, channel) for set alerts that only ever failed, newer than `since`."""
        rows = self.db.execute(
            f"SELECT set_alerts.kind, set_alerts.channel, {SET_COLUMNS} FROM set_alerts"
            " JOIN sets ON sets.source = set_alerts.source AND sets.set_id = set_alerts.set_id"
            " WHERE set_alerts.source = ?"
            " GROUP BY set_alerts.source, set_alerts.set_id, set_alerts.kind, set_alerts.channel"
            " HAVING MAX(set_alerts.ok) = 0 AND MIN(set_alerts.sent_at) >= ?",
            (source, since.isoformat()),
        ).fetchall()
        return [(_announcement(r[2:]), r[0], r[1]) for r in rows]

    def failure_streak(self, source: str) -> tuple[int, datetime | None]:
        """(failed checks in a row up to now, time of the latest one)."""
        count, last = self.db.execute(
            "SELECT COUNT(*), MAX(checked_at) FROM source_checks WHERE source = ? AND ok = 0"
            " AND id > COALESCE((SELECT MAX(id) FROM source_checks WHERE source = ? AND ok = 1), 0)",
            (source, source),
        ).fetchone()
        return count, datetime.fromisoformat(last) if last else None

    def is_marked_broken(self, source: str) -> bool:
        return self.db.execute("SELECT 1 FROM broken_sources WHERE source = ?", (source,)).fetchone() is not None

    def mark_broken(self, source: str, broken: bool) -> None:
        with self.db:
            if broken:
                self.db.execute("INSERT OR IGNORE INTO broken_sources (source) VALUES (?)", (source,))
            else:
                self.db.execute("DELETE FROM broken_sources WHERE source = ?", (source,))

    def last_successful_check(self, source: str) -> datetime | None:
        row = self.db.execute("SELECT MAX(checked_at) FROM source_checks WHERE source = ? AND ok = 1",
                              (source,)).fetchone()
        return datetime.fromisoformat(row[0]) if row[0] else None

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
