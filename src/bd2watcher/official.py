import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from bd2watcher.adapters.html import text_of
from bd2watcher.classify import normalise
from bd2watcher.config import Config, Source
from bd2watcher.cycle import EmptyResult
from bd2watcher.models import Announcement, SetAlert
from bd2watcher.store import Store

log = logging.getLogger(__name__)

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
JP_DATE = re.compile(r"(\d{4})\s*[年/.]\s*(\d{1,2})\s*[月/.]\s*(\d{1,2})")
EN_DATE = re.compile(r"\b([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", re.IGNORECASE)


def parse_date(text: str) -> date | None:
    """2026年7月3日, 2026/07/03, 2026.07.03, July 3, 2026 or Jul. 3, 2026."""
    text = normalise(text)
    try:
        if m := JP_DATE.search(text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if (m := EN_DATE.search(text)) and m[1].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    except ValueError:
        return None
    return None


def fetch(source: Source, config: Config, fetcher) -> list[Announcement]:
    """Every product link on the official list page, with its title and the release date found near it."""
    page_url = urljoin(source.base_url, source.official.list_path)
    tree = HTMLParser(fetcher.get_text(page_url))
    pattern = re.compile(source.official.link_pattern)
    found: dict[str, Announcement] = {}
    for link in tree.css("a[href]"):
        url = urljoin(page_url, link.attributes["href"])
        path = urlsplit(url).path
        if urlsplit(url).netloc != urlsplit(page_url).netloc or not pattern.search(path):
            continue
        set_id = path.rstrip("/").rsplit("/", 1)[-1]
        title = text_of(link) or (link.css_first("img").attributes.get("alt", "") if link.css_first("img") else "")
        release = None
        node = link
        for _ in range(3):  # the date usually sits in the product's card, a level or two up
            node = node.parent
            if node is None:
                break
            if release := parse_date(text_of(node)):
                break
        previous = found.get(set_id)
        if previous is None or len(title) > len(previous.title) or (release and not previous.release_date):
            found[set_id] = Announcement(
                source=source.name, set_id=set_id, title=title or (previous.title if previous else set_id),
                language=source.official.language, url=url, series=series_of_set(set_id, title, config),
                release_date=release or (previous.release_date if previous else None),
            )
    return list(found.values())


def series_of_set(set_id: str, title: str, config: Config) -> str:
    folded = normalise(title)
    for watchlist in config.watchlists:
        if any(normalise(k) in folded for k in watchlist.keywords):
            return watchlist.series
        if any(set_id.lower().startswith(f"{code.lower()}_") or set_id.lower() == code.lower()
               for code in watchlist.set_codes):
            return watchlist.series
    return ""


def run_official_check(source: Source, config: Config, fetcher, store: Store, now: datetime, notifiers=()) -> None:
    """One check of an official site: new watched-series sets alert now, other new sets wait for the digest."""
    try:
        announcements = fetch(source, config, fetcher)
        if not announcements and store.has_successful_check(source.name):
            raise EmptyResult(f"{source.name} listed no products at all")
    except Exception as e:
        store.record_check(source.name, now, ok=False, listing_count=0, error=f"{type(e).__name__}: {e}")
        raise

    baseline = not store.has_successful_check(source.name)
    known = {s.set_id for s in store.sets(source.name)}
    new = [a for a in announcements if a.set_id not in known]
    store.save_sets(announcements, now, queue_for_digest=[] if baseline else [a for a in new if not a.series])
    store.record_check(source.name, now, ok=True, listing_count=len(announcements))

    cooldown = timedelta(hours=config.alerts.cooldown_hours)
    for announcement, kind, label in store.undelivered_set_alerts(source.name, since=now - cooldown):
        for n in notifiers:
            if n.label == label:
                _send(n, kind, announcement, source, store, now)
    if baseline:
        return
    for announcement in (a for a in new if a.series):
        kind = "english_release" if announcement.language == "EN" else "new_set"
        for n in notifiers:
            if n.channel in ("discord",):
                _send(n, kind, announcement, source, store, now)


def _send(notifier, kind: str, announcement: Announcement, source: Source, store: Store, now: datetime) -> None:
    alert = SetAlert(kind, notifier.label, announcement, source.display_name, now)
    try:
        notifier.send(alert)
        store.record_set_alert(alert, ok=True)
    except Exception as e:
        log.exception("Sending %s alert to %s failed", kind, notifier.label)
        store.record_set_alert(alert, ok=False, error=f"{type(e).__name__}: {e}")
