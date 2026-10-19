import re
import unicodedata

from bd2watcher.config import Config
from bd2watcher.models import Kind, RawListing, StockState


def normalise(text: str) -> str:
    """Fold case and full-width/half-width differences so ＢｒｏｗｎＤｕｓｔ２ matches BrownDust2."""
    return unicodedata.normalize("NFKC", text).casefold()


def series_of(raw: RawListing, config: Config) -> str | None:
    title = normalise(raw.title)
    for watchlist in config.watchlists:
        if any(normalise(k) in title for k in watchlist.keywords):
            return watchlist.series
    return None


def kind_of(raw: RawListing, config: Config) -> Kind | None:
    """Return sealed, supply or other, or None for a single card."""
    rules = config.kinds
    title = unicodedata.normalize("NFKC", raw.title)
    if raw.product_type in rules.single.product_types:
        return None
    if any(re.search(p, title, re.IGNORECASE) for p in rules.single.patterns):
        return None
    folded = normalise(raw.title)
    if any(normalise(k) in folded for k in rules.supply):
        return "supply"
    if any(normalise(k) in folded for k in rules.sealed):
        return "sealed"
    return "other"


def product_of(raw: RawListing, series: str, kind: str, config: Config) -> str:
    """Name the product so the same box at different stores lands in one dashboard row."""
    if kind != "sealed":
        return raw.title
    title = normalise(raw.title)
    language = "EN" if any(normalise(m) in f" {title} " for m in config.english_markers) else "JP"
    for rule in config.products:
        if any(normalise(k) in title for k in rule.keywords):
            return f"{series} {rule.name} ({language})"
    return raw.title


def stock_state_of(raw: RawListing, config: Config) -> StockState:
    if raw.available is None:
        return "unknown"
    if not raw.available:
        return "sold_out"
    text = normalise(" ".join((raw.title, *raw.tags)))
    if any(normalise(m) in text for m in config.preorder_markers):
        return "preorder"
    return "in_stock"
