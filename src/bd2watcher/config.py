from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator


class Intervals(BaseModel):
    store_minutes: int = 10
    official_minutes: int = 60


class Watchlist(BaseModel):
    series: str
    keywords: list[str]
    set_codes: list[str] = []  # official product URL codes, e.g. "brd" for /products/brd_bp/


class SingleRules(BaseModel):
    patterns: list[str] = []
    product_types: list[str] = []


class KindRules(BaseModel):
    single: SingleRules = SingleRules()
    supply: list[str] = []
    sealed: list[str] = []


class Alerts(BaseModel):
    cooldown_hours: float = 6
    dry_run: bool = False


class ProductRule(BaseModel):
    name: str
    keywords: list[str]


class HtmlSelectors(BaseModel):
    """How to read a non-Shopify store's listing pages. Selectors are CSS, relative to each product."""

    list_path: str
    product: str
    title: str
    link: str
    price: str | None = None
    stock: str | None = None
    next_page: str | None = None
    max_pages: int = 10
    # Stock text patterns, checked in this order: sold out, then preorder, then in stock.
    sold_out: list[str] = ["out of stock", "not in stock", "sold out", "unavailable", "not available", "品切れ", "在庫切れ", "売り切れ", "完売"]
    preorder: list[str] = ["pre-order", "preorder", "backorder", "予約"]
    in_stock: list[str] = ["in stock", "add to cart", "available", "在庫あり", "カートに入れる"]


class OfficialSite(BaseModel):
    """How to read an official Weiss Schwarz site's product list."""

    language: Literal["JP", "EN"]
    list_path: str = "/products/"
    link_pattern: str = r"/products/[\w-]+/?$"  # one product page per set


class Source(BaseModel):
    name: str
    label: str | None = None
    adapter: Literal["shopify", "html", "official"]
    base_url: str
    products_path: str = "/products.json"
    enabled: bool = True
    html: HtmlSelectors | None = None
    official: OfficialSite | None = None
    currency: str = ""

    @model_validator(mode="after")
    def _check_adapter_settings(self):
        if self.adapter == "html" and self.html is None:
            raise ValueError(f"source {self.name!r} uses the html adapter but has no html: selectors")
        if self.adapter != "official" and not self.currency:
            raise ValueError(f"store {self.name!r} needs a currency")
        if self.adapter == "official" and self.official is None:
            raise ValueError(f"source {self.name!r} uses the official adapter but has no official: settings")
        return self

    @property
    def is_official(self) -> bool:
        return self.adapter == "official"

    @property
    def display_name(self) -> str:
        return self.label or self.name


class Config(BaseModel):
    intervals: Intervals = Intervals()
    alerts: Alerts = Alerts()
    user_agent: str
    watchlists: list[Watchlist]
    kinds: KindRules
    preorder_markers: list[str] = []
    products: list[ProductRule] = []
    english_markers: list[str] = []
    sources: list[Source]

    @property
    def enabled_sources(self) -> list[Source]:
        return [s for s in self.sources if s.enabled]

    def source(self, name: str) -> Source:
        for source in self.sources:
            if source.name == name:
                return source
        raise KeyError(f"No source named {name!r} in config")


def load_config(path: Path | str) -> Config:
    with open(path, encoding="utf-8") as f:
        return Config.model_validate(yaml.safe_load(f))
