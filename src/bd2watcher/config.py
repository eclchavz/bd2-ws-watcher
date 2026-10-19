from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class Intervals(BaseModel):
    store_minutes: int = 10
    official_minutes: int = 60


class Watchlist(BaseModel):
    series: str
    keywords: list[str]


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


class Source(BaseModel):
    name: str
    label: str | None = None
    adapter: Literal["shopify"]
    base_url: str
    products_path: str = "/products.json"
    currency: str
    enabled: bool = True

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
