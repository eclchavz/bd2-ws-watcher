from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

StockState = Literal["in_stock", "preorder", "sold_out", "unknown"]
Kind = Literal["sealed", "supply", "other"]
EventKind = Literal["new_listing", "restock", "preorder_opened", "price_changed"]
SetEventKind = Literal["new_set", "english_release"]


@dataclass(frozen=True)
class RawListing:
    """What an adapter found for one product at one store, before classification."""

    external_id: str
    title: str
    url: str
    price: Decimal | None
    available: bool | None
    product_type: str
    tags: tuple[str, ...]
    stock_state: StockState | None = None  # set when the adapter already knows it (html stock text)


@dataclass(frozen=True)
class Listing:
    source: str
    external_id: str
    title: str
    url: str
    series: str
    kind: Kind
    price: Decimal | None
    currency: str
    stock_state: StockState
    product: str = ""  # the product this listing sells, shared across stores, e.g. "Brown Dust 2 Booster Box (JP)"


@dataclass(frozen=True)
class Check:
    checked_at: datetime
    ok: bool
    listing_count: int
    error: str | None


@dataclass(frozen=True)
class Event:
    kind: EventKind
    listing: Listing
    at: datetime


@dataclass(frozen=True)
class Alert:
    """An event delivered (or attempted) through one channel."""

    event: EventKind
    channel: str
    listing: Listing
    store_label: str
    sent_at: datetime
    ok: bool = True
    usd_rate: Decimal | None = None  # for showing an approximate USD price next to other currencies


@dataclass(frozen=True)
class Announcement:
    """A set or product announced on an official Weiss Schwarz site."""

    source: str
    set_id: str
    title: str
    language: str
    url: str
    series: str  # the watched series it belongs to, or "" for any other series
    release_date: date | None = None


@dataclass(frozen=True)
class SetAlert:
    event: SetEventKind
    channel: str
    announcement: Announcement
    source_label: str
    sent_at: datetime
    ok: bool = True


@dataclass(frozen=True)
class PricePoint:
    price: Decimal
    currency: str
    at: datetime
