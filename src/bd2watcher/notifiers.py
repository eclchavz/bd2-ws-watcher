import logging
from decimal import Decimal
import smtplib
from email.message import EmailMessage
from urllib.parse import urlsplit

import httpx

from bd2watcher.models import Alert, Announcement, SetAlert, SourceAlert

log = logging.getLogger(__name__)

HEADLINES = {
    "new_listing": "🆕 NEW",
    "restock": "🟢 IN STOCK",
    "preorder_opened": "📦 PREORDER OPEN",
    "new_set": "📣 ANNOUNCED",
    "english_release": "🇺🇸 ENGLISH RELEASE ANNOUNCED",
    "price_changed": "💲 PRICE CHANGED",  # never routed to a channel, but formattable
    "source_broken": "⚠️ CHECK BROKEN",
    "source_recovered": "✅ CHECK RECOVERED",
}
STOCK_WORDS = {"in_stock": "in stock", "preorder": "preorder", "sold_out": "sold out", "unknown": "stock unknown"}


def usd(price: Decimal, rate: Decimal) -> Decimal:
    return (price * rate).quantize(Decimal("0.01"))


def price_text(price: Decimal | None, currency: str, rate: Decimal | None) -> str:
    """'54.99 USD', or '6200 JPY (~$41.54)' when a USD rate is known."""
    if price is None:
        return "price unknown"
    if currency != "USD" and rate is not None:
        return f"{price} {currency} (~${usd(price, rate)})"
    return f"{price} {currency}"


def format_alert(alert: Alert | SetAlert | SourceAlert) -> str:
    if isinstance(alert, SourceAlert):
        if alert.event == "source_broken":
            return (f"**{HEADLINES[alert.event]}** · {alert.source_label}\n"
                    f"Several checks in a row failed, so alerts from it may be missed. Last error: {alert.error}")
        return f"**{HEADLINES[alert.event]}** · {alert.source_label}\nChecks are working again."
    if isinstance(alert, SetAlert):
        a = alert.announcement
        release = f"releases {a.release_date.isoformat()}" if a.release_date else "release date not given yet"
        return f"**{HEADLINES[alert.event]}** · {a.title}\n{alert.source_label} · {release}\n{a.url}"
    l = alert.listing
    price = price_text(l.price, l.currency, alert.usd_rate)
    return (
        f"**{HEADLINES[alert.event]}** · {l.title}\n"
        f"{alert.store_label} · {price} · {STOCK_WORDS[l.stock_state]}\n"
        f"{l.url}"
    )


def plain_headline(alert: Alert | SetAlert) -> str:
    """The headline without its emoji, for email subjects and push titles: "IN STOCK: <title>"."""
    words = HEADLINES[alert.event].split(" ", 1)[1]
    title = alert.announcement.title if isinstance(alert, SetAlert) else alert.listing.title
    return f"{words}: {title}"


def plain_body(alert: Alert | SetAlert) -> str:
    return format_alert(alert).split("\n", 1)[1]


def alert_url(alert: Alert | SetAlert) -> str:
    return alert.announcement.url if isinstance(alert, SetAlert) else alert.listing.url


def format_digest(announcements: list[Announcement]) -> str:
    lines = []
    for a in announcements:
        when = a.release_date.isoformat() if a.release_date else "date TBA"
        lines.append(f"- {a.title} ({a.language}, {when})\n  {a.url}")
    return "New Weiss Schwarz sets announced since the last digest:\n\n" + "\n".join(lines) + "\n"


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


class EmailNotifier:
    """Gmail over SMTP with an app password, from and to the same address."""

    channel = label = "email"

    def __init__(self, address: str, app_password: str, smtp=smtplib.SMTP_SSL):
        self.address = address
        self.app_password = app_password
        self.smtp = smtp

    def send(self, alert: Alert | SetAlert) -> None:
        self._mail(plain_headline(alert), plain_body(alert))

    def send_digest(self, announcements: list[Announcement]) -> None:
        count = len(announcements)
        self._mail(f"{count} new Weiss Schwarz set{'s' if count != 1 else ''}", format_digest(announcements))

    def _mail(self, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = message["To"] = self.address
        message["Subject"] = subject
        message.set_content(body)
        with self.smtp("smtp.gmail.com", 465, timeout=30) as smtp:
            smtp.login(self.address, self.app_password)
            smtp.sendmail(self.address, [self.address], message.as_string())


class NtfyNotifier:
    """Push notifications through ntfy. NTFY_URL is the topic URL, e.g. https://ntfy.sh/some-private-topic."""

    channel = label = "ntfy"

    def __init__(self, topic_url: str, transport: httpx.BaseTransport | None = None):
        parts = urlsplit(topic_url)
        prefix, _, topic = parts.path.strip("/").rpartition("/")
        if parts.scheme not in ("http", "https") or not parts.netloc or not topic:
            raise ValueError(f"NTFY_URL must look like https://ntfy.sh/your-topic, not {topic_url!r}")
        self.server = f"{parts.scheme}://{parts.netloc}/{prefix + '/' if prefix else ''}"
        self.topic = topic
        self.client = httpx.Client(timeout=20, transport=transport)

    def send(self, alert: Alert | SetAlert) -> None:
        response = self.client.post(self.server, json={
            "topic": self.topic, "title": plain_headline(alert), "message": plain_body(alert),
            "click": alert_url(alert),
        })
        response.raise_for_status()


class DryRunNotifier:
    """Logs instead of sending. Stands in for a real channel so routing stays the same."""

    dry_run = True

    def __init__(self, channel: str):
        self.channel = channel
        self.label = f"dry-run {channel}"

    def send(self, alert: Alert | SetAlert) -> None:
        log.info("[dry-run %s] %s", self.channel, format_alert(alert).replace("\n", " | "))

    def send_digest(self, announcements: list[Announcement]) -> None:
        log.info("[dry-run %s] digest: %s", self.channel, format_digest(announcements).replace("\n", " | "))
