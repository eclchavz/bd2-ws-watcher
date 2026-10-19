from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

StockState = Literal["in_stock", "preorder", "sold_out", "unknown"]
Kind = Literal["sealed", "supply", "other"]
EventKind = Literal["new_listing", "restock", "preorder_opened"]


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
