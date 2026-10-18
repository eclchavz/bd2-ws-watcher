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
}


def deliver(events: list[Event], source: Source, config: Config, store: Store, notifiers, now: datetime) -> None:
    """Send each event to its channels, at most once per listing per cooldown window."""
    cooldown = timedelta(hours=config.alerts.cooldown_hours)
    for event in events:
        event_id = store.record_event(event)
        last = store.last_alert_at(event.listing.source, event.listing.external_id)
        if last is not None and now - last < cooldown:
            log.info("Cooldown: not alerting %s for %s", event.kind, event.listing.title)
            continue
        for notifier in notifiers:
            if notifier.channel not in ROUTES[event.kind]:
                continue
            alert = Alert(event.kind, getattr(notifier, "label", notifier.channel), event.listing, source.label, now)
            try:
                notifier.send(alert)
                store.record_alert(event_id, alert, ok=True)
            except Exception as e:
                log.exception("Sending %s alert to %s failed", event.kind, notifier.channel)
                store.record_alert(event_id, alert, ok=False, error=f"{type(e).__name__}: {e}")
