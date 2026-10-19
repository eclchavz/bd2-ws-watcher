import logging

import httpx

from bd2watcher.models import Alert, SetAlert

log = logging.getLogger(__name__)

HEADLINES = {
    "new_listing": "🆕 NEW",
    "restock": "🟢 IN STOCK",
    "preorder_opened": "📦 PREORDER OPEN",
    "new_set": "📣 ANNOUNCED",
    "english_release": "🇺🇸 ENGLISH RELEASE ANNOUNCED",
}
STOCK_WORDS = {"in_stock": "in stock", "preorder": "preorder", "sold_out": "sold out", "unknown": "stock unknown"}


def format_alert(alert: Alert | SetAlert) -> str:
    if isinstance(alert, SetAlert):
        a = alert.announcement
        release = f"releases {a.release_date.isoformat()}" if a.release_date else "release date not given yet"
        return f"**{HEADLINES[alert.event]}** · {a.title}\n{alert.source_label} · {release}\n{a.url}"
    l = alert.listing
    price = "price unknown" if l.price is None else f"{l.price} {l.currency}"
    return (
        f"**{HEADLINES[alert.event]}** · {l.title}\n"
        f"{alert.store_label} · {price} · {STOCK_WORDS[l.stock_state]}\n"
        f"{l.url}"
    )


class DiscordNotifier:
    channel = label = "discord"

    def __init__(self, webhook_url: str, transport: httpx.BaseTransport | None = None):
        self.webhook_url = webhook_url
        self.client = httpx.Client(timeout=20, transport=transport)

    def send(self, alert: Alert) -> None:
        response = self.client.post(
            self.webhook_url,
            json={"content": format_alert(alert), "allowed_mentions": {"parse": []}},
        )
        response.raise_for_status()


class DryRunNotifier:
    """Logs instead of sending. Stands in for a real channel so routing stays the same."""

    label = "dry-run"

    def __init__(self, channel: str):
        self.channel = channel

    def send(self, alert: Alert) -> None:
        log.info("[dry-run %s] %s", self.channel, format_alert(alert).replace("\n", " | "))
