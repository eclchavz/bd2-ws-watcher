import logging

from bd2watcher.store import Store

log = logging.getLogger(__name__)


def run_digest(store: Store, notifiers) -> None:
    """Email the queued Weiss Schwarz sets as one message, then clear the queue. Quiet days send nothing.

    If sending fails, or it's a dry run, the queue is kept and goes out with the next digest.
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
            notifier.send_digest(queue)
    except Exception:
        log.exception("Sending the digest failed; keeping %d sets for next time", len(queue))
        return
    if any(getattr(n, "dry_run", False) for n in senders):
        return
    store.clear_digest_queue(queue)
