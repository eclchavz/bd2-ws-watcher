from datetime import datetime

from bd2watcher.adapters import html, shopify
from bd2watcher.alerts import deliver
from bd2watcher.changes import detect
from bd2watcher.classify import kind_of, product_of, series_of, stock_state_of
from bd2watcher.config import Config, Source
from bd2watcher.models import Listing, RawListing
from bd2watcher.store import Store

ADAPTERS = {"shopify": shopify.fetch, "html": html.fetch}


class EmptyResult(Exception):
    """A source that used to have products returned none, which means it's broken, not sold out."""


def find_watched(source: Source, config: Config, fetcher) -> list[Listing]:
    """Fetch a source and keep only watched sealed and supply listings. Writes nothing."""
    return watched(source, config, ADAPTERS[source.adapter](source, fetcher))


def watched(source: Source, config: Config, raws: list[RawListing]) -> list[Listing]:
    found = []
    for raw in raws:
        series = series_of(raw, config)
        if series is None:
            continue
        kind = kind_of(raw, config)
        if kind not in ("sealed", "supply"):
            continue
        found.append(
            Listing(
                source=source.name, external_id=raw.external_id, title=raw.title, url=raw.url,
                series=series, kind=kind, price=raw.price, currency=source.currency,
                stock_state=stock_state_of(raw, config), product=product_of(raw, series, kind, config),
            )
        )
    return found


def run_check(source: Source, config: Config, fetcher, store: Store, now: datetime,
              notifiers=()) -> list[Listing]:
    """One check of one source: fetch, classify, compare with stored state, save, alert.

    The first successful check of a source is a silent baseline. A failure is recorded, then re-raised.
    """
    try:
        raws = ADAPTERS[source.adapter](source, fetcher)
        if not raws and store.has_successful_check(source.name):
            raise EmptyResult(f"{source.name} returned no products at all")
        listings = watched(source, config, raws)
    except Exception as e:
        store.record_check(source.name, now, ok=False, listing_count=0, error=f"{type(e).__name__}: {e}")
        raise
    previous = {l.external_id: l for l in store.listings(source.name)}
    baseline = not store.has_successful_check(source.name)
    events = [] if baseline else detect(previous, listings, now)

    current_ids = {l.external_id for l in listings}
    missing = [i for i, l in previous.items() if i not in current_ids and l.stock_state != "sold_out"]
    store.save_listings(listings, now)
    for l in listings:
        before = previous.get(l.external_id)
        if l.price is not None and (before is None or before.price != l.price
                                    or not store.price_history(l.source, l.external_id)):
            store.add_price_point(l, now)
    store.mark_sold_out(source.name, missing)
    store.record_check(source.name, now, ok=True, listing_count=len(listings))
    deliver(events, source, config, store, notifiers, now)
    return listings
