from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

StockState = Literal["in_stock", "preorder", "sold_out", "unknown"]
Kind = Literal["sealed", "supply", "other"]


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
