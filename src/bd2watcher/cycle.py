from datetime import datetime

from bd2watcher.adapters import shopify
from bd2watcher.classify import kind_of, series_of, stock_state_of
from bd2watcher.config import Config, Source
from bd2watcher.models import Listing
from bd2watcher.store import Store

ADAPTERS = {"shopify": shopify.fetch}


def find_watched(source: Source, config: Config, fetcher) -> list[Listing]:
    """Fetch a source and keep only watched sealed and supply listings. Writes nothing."""
    found = []
    for raw in ADAPTERS[source.adapter](source, fetcher):
        series = series_of(raw, config)
        kind = kind_of(raw, config)
        if series is None or kind not in ("sealed", "supply"):
            continue
        found.append(
            Listing(
                source=source.name, external_id=raw.external_id, title=raw.title, url=raw.url,
                series=series, kind=kind, price=raw.price, currency=source.currency,
                stock_state=stock_state_of(raw, config),
            )
        )
    return found


def run_check(source: Source, config: Config, fetcher, store: Store, now: datetime) -> list[Listing]:
    """One check of one source: fetch, classify, save."""
    listings = find_watched(source, config, fetcher)
    store.save_listings(listings, now)
    store.record_check(source.name, now, ok=True, listing_count=len(listings))
    return listings
