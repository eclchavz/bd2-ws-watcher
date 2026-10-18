from datetime import datetime

from bd2watcher.models import Event, Listing


def detect(previous: dict[str, Listing], current: list[Listing], at: datetime) -> list[Event]:
    """Compare a check's listings with stored state and return what changed for the better."""
    events = []
    for listing in current:
        before = previous.get(listing.external_id)
        if before is None:
            events.append(Event("new_listing", listing, at))
        elif listing.stock_state == "preorder" and before.stock_state != "preorder":
            events.append(Event("preorder_opened", listing, at))
        elif listing.stock_state == "in_stock" and before.stock_state in ("sold_out", "preorder"):
            events.append(Event("restock", listing, at))
    return events
