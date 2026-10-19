import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from urllib.parse import urlsplit

import httpx

from bd2watcher.models import Alert, Announcement, SetAlert

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

    def send_digest(self, announcements: list[Announcement], now: datetime) -> None:
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
        self.server = f"{parts.scheme}://{parts.netloc}/"
        self.topic = parts.path.strip("/")
        self.client = httpx.Client(timeout=20, transport=transport)

    def send(self, alert: Alert | SetAlert) -> None:
        response = self.client.post(self.server, json={
            "topic": self.topic, "title": plain_headline(alert), "message": plain_body(alert),
            "click": alert_url(alert),
        })
        response.raise_for_status()


class DryRunNotifier:
    """Logs instead of sending. Stands in for a real channel so routing stays the same."""

    label = "dry-run"

    def __init__(self, channel: str):
        self.channel = channel

    def send(self, alert: Alert | SetAlert) -> None:
        log.info("[dry-run %s] %s", self.channel, format_alert(alert).replace("\n", " | "))

    def send_digest(self, announcements: list[Announcement], now: datetime) -> None:
        log.info("[dry-run %s] digest: %s", self.channel, format_digest(announcements).replace("\n", " | "))
