import logging
from datetime import datetime

from bd2watcher.config import Config
from bd2watcher.store import Store

log = logging.getLogger(__name__)


def run_digest(config: Config, store: Store, notifiers, now: datetime) -> None:
    """Email the queued Weiss Schwarz sets as one message, then clear the queue. Quiet days send nothing.

    If sending fails, the queue is kept and goes out with tomorrow's digest.
    """
    queue = store.digest_queue()
    if not queue:
        return
    senders = [n for n in notifiers if n.channel == "email" and hasattr(n, "send_digest")]
    if not senders:
        log.warning("%d sets are waiting for the digest, but email isn't set up", len(queue))
        return
    try:
        for notifier in senders:
            notifier.send_digest(queue, now)
    except Exception:
        log.exception("Sending the digest failed; keeping %d sets for next time", len(queue))
        return
    store.clear_digest_queue(queue)
