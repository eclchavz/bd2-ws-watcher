import logging
from datetime import datetime, timedelta

from bd2watcher.alerts import ROUTES, send
from bd2watcher.config import Config, Source
from bd2watcher.models import SourceAlert
from bd2watcher.store import Store

log = logging.getLogger(__name__)

BROKEN_AFTER = 3
MAX_BACKOFF = timedelta(hours=2)


def interval(source: Source, config: Config) -> timedelta:
    return timedelta(minutes=config.intervals.official_minutes if source.is_official else config.intervals.store_minutes)


def due(source: Source, config: Config, store: Store, now: datetime) -> bool:
    """Whether a failing source should be tried again: wait interval x 2^(failures - 1), at most 2 hours."""
    failures, last = store.failure_streak(source.name)
    if failures == 0:
        return True
    wait = min(interval(source, config) * 2 ** (failures - 1), MAX_BACKOFF)
    return now - last >= wait


def after_check(source: Source, store: Store, notifiers, now: datetime, error: str | None) -> None:
    """Send source_broken when a source reaches 3 failed checks in a row, and source_recovered when it comes back.

    Call after the check has been recorded.
    """
    failures, _ = store.failure_streak(source.name)
    if error is not None and failures == BROKEN_AFTER:
        _notify("source_broken", source, store, notifiers, now, error)
    elif error is None and store.failures_before_last_check(source.name) >= BROKEN_AFTER:
        _notify("source_recovered", source, store, notifiers, now, None)


def _notify(kind: str, source: Source, store: Store, notifiers, now: datetime, error: str | None) -> None:
    for notifier in notifiers:
        if notifier.channel in ROUTES[kind]:
            alert = SourceAlert(kind, notifier.label, source.name, source.display_name, error, now)
            send(notifier, alert, lambda ok, err=None: log.info("%s for %s via %s: %s", kind, source.name,
                                                                 notifier.label, "sent" if ok else err))
