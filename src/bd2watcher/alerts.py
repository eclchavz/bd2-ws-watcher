import logging
from datetime import datetime, timedelta

from bd2watcher.config import Config, Source
from bd2watcher.models import Alert, Event
from bd2watcher.store import Store

log = logging.getLogger(__name__)

# Which channels each event goes to. Email joins these in ticket 08.
ROUTES = {
    "new_listing": ("discord",),
    "restock": ("discord",),
    "preorder_opened": ("discord",),
    "new_set": ("discord",),           # watched-series sets only; others go to the digest
    "english_release": ("discord",),
}


def deliver(events: list[Event], source: Source, config: Config, store: Store, notifiers, now: datetime) -> None:
    """Retry earlier failed sends, then send each new event to its channels.

    A listing gets at most one alert of each event kind per cooldown window (ADR 0002).
    """
    cooldown = timedelta(hours=config.alerts.cooldown_hours)
    by_label = {n.label: n for n in notifiers}
    current = {l.external_id: l for l in store.listings(source.name)}

    for event_id, label, event in store.undelivered(source.name, since=now - cooldown):
        still_true = current.get(event.listing.external_id)
        if label in by_label and still_true and still_true.stock_state == event.listing.stock_state:
            _send(by_label[label], event_id, event, source, store, now)

    for event in events:
        event_id = store.record_event(event)
        last = store.last_alert_at(event.listing.source, event.listing.external_id, event.kind)
        if last is not None and now - last < cooldown:
            log.info("Cooldown: not alerting %s for %s", event.kind, event.listing.title)
            continue
        for notifier in notifiers:
            if notifier.channel in ROUTES[event.kind]:
                _send(notifier, event_id, event, source, store, now)


def _send(notifier, event_id: int, event: Event, source: Source, store: Store, now: datetime) -> None:
    alert = Alert(event.kind, notifier.label, event.listing, source.display_name, now)
    send(notifier, alert, lambda ok, error=None: store.record_alert(event_id, alert, ok=ok, error=error))


def send(notifier, alert, record) -> None:
    """Send one alert and record the outcome. A failure is logged and recorded, never raised."""
    try:
        notifier.send(alert)
        record(True)
    except Exception as e:
        log.exception("Sending %s alert to %s failed", alert.event, notifier.label)
        record(False, f"{type(e).__name__}: {e}")
