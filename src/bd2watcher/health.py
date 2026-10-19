import logging
from datetime import datetime, timedelta

from bd2watcher.alerts import ROUTES, send
from bd2watcher.config import Config, Source
from bd2watcher.models import SourceAlert
from bd2watcher.store import Store

log = logging.getLogger(__name__)

BROKEN_AFTER = 3
MAX_BACKOFF = timedelta(hours=2)
JITTER_ALLOWANCE = 0.25  # of an interval: the scheduler fires up to 10% early or late


def interval(source: Source, config: Config) -> timedelta:
    return timedelta(minutes=config.intervals.official_minutes if source.is_official else config.intervals.store_minutes)


def due(source: Source, config: Config, store: Store, now: datetime) -> bool:
    """Whether a failing source should be tried again: wait interval x 2^(failures - 1), at most 2 hours."""
    failures, last = store.failure_streak(source.name)
    if failures == 0:
        return True
    every = interval(source, config)
    wait = min(every * 2 ** (failures - 1), MAX_BACKOFF)
    return now - last >= wait - every * JITTER_ALLOWANCE


def after_check(source: Source, store: Store, notifiers, now: datetime, error: str | None) -> None:
    """Tell Discord when a source breaks (3 failed checks in a row) and when it recovers.

    Whether a source is broken is stored, not inferred, so a notice that fails to send is retried after the
    next check, and "recovered" is only ever sent after "broken" was.
    """
    broken = store.is_marked_broken(source.name)
    if error is not None and not broken and store.failure_streak(source.name)[0] >= BROKEN_AFTER:
        if _notify("source_broken", source, notifiers, now, error):
            store.mark_broken(source.name, True)
    elif error is None and broken:
        if _notify("source_recovered", source, notifiers, now, None):
            store.mark_broken(source.name, False)


def safely_after_check(source: Source, store: Store, notifiers, now: datetime, error: str | None) -> None:
    """after_check that never raises, so a health problem can't hide or break the check itself."""
    try:
        after_check(source, store, notifiers, now, error)
    except Exception:
        log.exception("Source health update for %s failed", source.name)


def _notify(kind: str, source: Source, notifiers, now: datetime, error: str | None) -> bool:
    """Send to every routed channel. True if at least one send succeeded."""
    delivered = []
    for notifier in notifiers:
        if notifier.channel in ROUTES[kind]:
            alert = SourceAlert(kind, notifier.label, source.name, source.display_name, error, now)
            send(notifier, alert, lambda ok, err=None: delivered.append(ok))
    return any(delivered)
