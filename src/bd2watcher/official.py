import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from bd2watcher.adapters.html import text_of
from bd2watcher import health
from bd2watcher.alerts import ROUTES, send
from bd2watcher.classify import normalise, series_of_title
from bd2watcher.config import Config, Source
from bd2watcher.cycle import EmptyResult
from bd2watcher.models import Announcement, SetAlert
from bd2watcher.store import Store

MONTHS = {name: i for i, names in enumerate([
    ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
    ("july", "jul"), ("august", "aug"), ("september", "sept", "sep"), ("october", "oct"),
    ("november", "nov"), ("december", "dec"),
], start=1) for name in names}
JP_DATE = re.compile(r"(\d{4})\s*[年/.]\s*(\d{1,2})\s*[月/.]\s*(\d{1,2})")
EN_DATE = re.compile(r"\b([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})\b")


def parse_date(text: str) -> date | None:
    """2026年7月3日, 2026/07/03, 2026.07.03, July 3, 2026 or Jul. 3, 2026. Skips lookalikes such as "Season 2, 2026"."""
    text = normalise(text)
    candidates = [(m.start(), (int(m[1]), int(m[2]), int(m[3]))) for m in JP_DATE.finditer(text)]
    candidates += [(m.start(), (int(m[3]), MONTHS[m[1]], int(m[2])))
                   for m in EN_DATE.finditer(text) if m[1] in MONTHS]
    for _, (year, month, day) in sorted(candidates):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def fetch(source: Source, config: Config, fetcher) -> list[Announcement]:
    """Every product link on the official list page, with its title and the release date in its own card."""
    page_url = urljoin(source.base_url, source.official.list_path)
    tree = HTMLParser(fetcher.get_text(page_url))
    pattern = re.compile(source.official.link_pattern)

    def set_id_of(link) -> str | None:
        url = urljoin(page_url, link.attributes.get("href") or "")
        if _host(url) != _host(page_url) or not pattern.search(urlsplit(url).path):
            return None
        return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]

    found: dict[str, Announcement] = {}
    for link in tree.css("a[href]"):
        set_id = set_id_of(link)
        if set_id is None:
            continue
        img = link.css_first("img")
        title = text_of(link) or (img.attributes.get("alt") or "" if img else "")
        release, node = None, link
        for _ in range(3):  # the date usually sits in the product's card, a level or two up
            node = node.parent
            if node is None:
                break
            ids_inside = {set_id_of(a) for a in node.css("a[href]")} - {None}
            if ids_inside - {set_id}:
                break  # this node holds other products too, so its dates aren't ours
            if release := parse_date(text_of(node)):
                break
        previous = found.get(set_id)
        found[set_id] = Announcement(
            source=source.name, set_id=set_id,
            title=max(title, previous.title if previous else "", key=len) or set_id,
            language=source.official.language, url=urljoin(page_url, link.attributes["href"]),
            series="", release_date=release or (previous.release_date if previous else None),
        )
    return [
        Announcement(a.source, a.set_id, a.title, a.language, a.url, series_of_set(a.set_id, a.title, config),
                     a.release_date)
        for a in found.values()
    ]


def series_of_set(set_id: str, title: str, config: Config) -> str:
    if series := series_of_title(title, config):
        return series
    for watchlist in config.watchlists:
        if any(set_id.lower() == c.lower() or set_id.lower().startswith(f"{c.lower()}_") for c in watchlist.set_codes):
            return watchlist.series
    return ""


def run_official_check(source: Source, config: Config, fetcher, store: Store, now: datetime, notifiers=()) -> None:
    """One check of an official site: watched-series sets alert now, other new sets wait for the digest.

    An official list page always has products, so an empty one is a failed check, even the first time.
    """
    try:
        announcements = fetch(source, config, fetcher)
        if not announcements:
            raise EmptyResult(f"{source.name} listed no products at all")
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        store.record_check(source.name, now, ok=False, listing_count=0, error=error)
        health.safely_after_check(source, store, notifiers, now, error)
        raise

    baseline = not store.has_successful_check(source.name)
    before = {s.set_id: s for s in store.sets(source.name)}
    new = [a for a in announcements if a.set_id not in before]
    # Watched now, but not before: either brand new, or newly recognised (retitled, or a new set code).
    newly_watched = [a for a in announcements if a.series and not (a.set_id in before and before[a.set_id].series)]
    store.save_sets(announcements, now, queue_for_digest=[] if baseline else [a for a in new if not a.series])
    store.record_check(source.name, now, ok=True, listing_count=len(announcements))
    health.safely_after_check(source, store, notifiers, now, None)

    cooldown = timedelta(hours=config.alerts.cooldown_hours)
    by_label = {n.label: n for n in notifiers}
    for announcement, kind, label in store.undelivered_set_alerts(source.name, since=now - cooldown):
        if label in by_label:
            _send(by_label[label], kind, announcement, source, store, now)
    if baseline:
        return
    for announcement in newly_watched:
        store.unqueue(source.name, announcement.set_id)
        kind = "english_release" if announcement.language == "EN" else "new_set"
        for n in notifiers:
            if n.channel in ROUTES[kind]:
                _send(n, kind, announcement, source, store, now)


def _send(notifier, kind: str, announcement: Announcement, source: Source, store: Store, now: datetime) -> None:
    alert = SetAlert(kind, notifier.label, announcement, source.display_name, now)
    send(notifier, alert, lambda ok, error=None: store.record_set_alert(alert, ok=ok, error=error))
