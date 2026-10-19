from datetime import datetime, timedelta, timezone
from email import message_from_string
from zoneinfo import ZoneInfo

import pytest

from bd2watcher.cycle import run_check
from bd2watcher.digest import run_digest
from bd2watcher.notifiers import EmailNotifier, NtfyNotifier
from bd2watcher.official import run_official_check
from conftest import FIXTURES, RecordingNotifier

PHOENIX = ZoneInfo("America/Phoenix")


class EmailRecorder(RecordingNotifier):
    channel = label = "email"

    def __init__(self):
        super().__init__()
        self.digests = []

    def send_digest(self, announcements):
        self.digests.append([a.title for a in announcements])


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.sent, self.login_args = host, port, [], None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, sender, recipients, message):
        self.sent.append((sender, recipients, message))


@pytest.fixture
def queued_sets(config, store, now):
    """Two other-series sets waiting in the digest queue."""
    from test_official_sites import NEW_OTHER_SET, Site, JP

    site = Site("https://ws-tcg.com", JP)
    run_official_check(config.source("official-jp"), config, site, store, now, [])
    site.add(NEW_OTHER_SET)
    site.add('<li><a href="/products/fr_bp2/">ブースターパック 葬送のフリーレン Vol.2</a></li>')
    run_official_check(config.source("official-jp"), config, site, store, now + timedelta(hours=1), [])
    return store


def test_a_brown_dust_2_restock_goes_to_discord_and_email(config, store, now, tcg_corner):
    discord, email = RecordingNotifier(), EmailRecorder()
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [discord, email])
    for v in tcg_corner.product(1003)["variants"]:
        v["available"] = True
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now + timedelta(minutes=10), [discord, email])

    assert sorted((a.event, a.channel) for a in store.alerts()) == [("restock", "discord"), ("restock", "email")]


def test_the_digest_sends_all_queued_sets_in_one_email_then_empties_the_queue(config, queued_sets):
    email = EmailRecorder()
    run_digest(queued_sets, [email])
    run_digest(queued_sets, [email])

    assert email.digests == [["ブースターパック 【推しの子】 Vol.3", "ブースターパック 葬送のフリーレン Vol.2"]]
    assert queued_sets.digest_queue() == []


def test_no_digest_email_on_a_quiet_day(config, store, now):
    email = EmailRecorder()
    run_digest(store, [email])
    assert email.digests == []


def test_a_failed_digest_keeps_the_queue_for_tomorrow(config, queued_sets, now):
    class Down(EmailRecorder):
        def send_digest(self, announcements):
            raise OSError("smtp down")

    run_digest(queued_sets, [Down()])
    assert len(queued_sets.digest_queue()) == 2


def test_email_goes_from_and_to_the_gmail_address_with_the_app_password(config, store, now, tcg_corner):
    FakeSMTP.instances.clear()
    email = EmailNotifier("me@gmail.com", "abcd efgh ijkl mnop", smtp=FakeSMTP)
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [email])
    for v in tcg_corner.product(1003)["variants"]:
        v["available"] = True
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now + timedelta(minutes=10), [email])

    [smtp] = FakeSMTP.instances
    assert (smtp.host, smtp.port, smtp.login_args) == ("smtp.gmail.com", 465, ("me@gmail.com", "abcd efgh ijkl mnop"))
    [(sender, recipients, raw)] = smtp.sent
    message = message_from_string(raw)
    assert (sender, recipients) == ("me@gmail.com", ["me@gmail.com"])
    assert "IN STOCK" in message["Subject"] and "Trial Deck" in message["Subject"]
    body = message.get_payload(decode=True).decode()
    assert "https://tcg-corner.com/products/weiss-schwarz-browndust2-trial-deck-japanese" in body


def test_digest_email_lists_each_set_with_date_and_link(config, queued_sets, now):
    FakeSMTP.instances.clear()
    run_digest(queued_sets, [EmailNotifier("me@gmail.com", "pw", smtp=FakeSMTP)])

    [smtp] = FakeSMTP.instances
    message = message_from_string(smtp.sent[0][2])
    body = message.get_payload(decode=True).decode()
    assert "2 new Weiss Schwarz sets" in message["Subject"]
    assert "【推しの子】 Vol.3" in body and "2026-11-13" in body and "https://ws-tcg.com/products/osk_bp/" in body


def test_ntfy_posts_the_alert_with_a_title_and_click_link():
    import httpx

    from bd2watcher.models import Alert, Listing
    from decimal import Decimal

    posted = []
    ntfy = NtfyNotifier("https://ntfy.sh/my-bd2-topic",
                        transport=httpx.MockTransport(lambda r: posted.append(r) or httpx.Response(200)))
    listing = Listing("tcg-corner", "1", "BD2 Booster Box", "https://shop.example/box", "Brown Dust 2", "sealed",
                      Decimal("54.99"), "USD", "in_stock")
    ntfy.send(Alert("restock", "ntfy", listing, "TCG Corner", datetime.now(timezone.utc)))

    [request] = posted
    import json
    body = json.loads(request.content)
    assert str(request.url) == "https://ntfy.sh/"
    assert (body["topic"], body["click"]) == ("my-bd2-topic", "https://shop.example/box")
    assert body["title"] == "IN STOCK: BD2 Booster Box"
    assert "TCG Corner · 54.99 USD · in stock" in body["message"]


def test_email_and_ntfy_come_from_env_and_are_optional(config, monkeypatch, caplog):
    from bd2watcher.cli import build_notifiers

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/hook")
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("NTFY_URL", raising=False)
    assert [n.channel for n in build_notifiers(config, dry_run=False)] == ["discord"]

    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pw")
    monkeypatch.setenv("NTFY_URL", "https://ntfy.sh/topic")
    assert [n.channel for n in build_notifiers(config, dry_run=False)] == ["discord", "email"]  # ntfy off in config
    config.alerts.ntfy = True
    assert [n.channel for n in build_notifiers(config, dry_run=False)] == ["discord", "email", "ntfy"]
    assert [n.label for n in build_notifiers(config, dry_run=True)] == [
        "dry-run discord", "dry-run email", "dry-run ntfy"]


def test_the_digest_fires_at_nine_arizona_time_every_day(config):
    from bd2watcher.cli import digest_trigger

    trigger = digest_trigger(config, "America/Phoenix")
    first = trigger.get_next_fire_time(None, datetime(2026, 10, 18, 8, 30, tzinfo=PHOENIX))
    second = trigger.get_next_fire_time(first, first + timedelta(seconds=1))
    assert first == datetime(2026, 10, 18, 9, 0, tzinfo=PHOENIX)
    assert second - first == timedelta(days=1)


def test_a_late_start_still_sends_that_mornings_digest(config):
    from bd2watcher.cli import DIGEST_JOB_OPTIONS

    assert DIGEST_JOB_OPTIONS["misfire_grace_time"] >= 3600 and DIGEST_JOB_OPTIONS["coalesce"] is True


def test_dry_run_digest_keeps_the_queue(config, queued_sets):
    from bd2watcher.notifiers import DryRunNotifier

    run_digest(queued_sets, [DryRunNotifier("email")])
    assert len(queued_sets.digest_queue()) == 2


@pytest.mark.parametrize("value", ["9:00 AM", "0900", "09:00:00", 540, "25:00"])
def test_a_bad_digest_time_is_rejected_when_config_loads(value):
    from bd2watcher.config import Alerts

    with pytest.raises(ValueError):
        Alerts(digest_time=value)


def test_ntfy_keeps_a_path_prefix_and_rejects_a_url_without_scheme():
    ntfy = NtfyNotifier("https://example.com/ntfy/bd2")
    assert (ntfy.server, ntfy.topic) == ("https://example.com/ntfy/", "bd2")
    with pytest.raises(ValueError):
        NtfyNotifier("ntfy.sh/topic")
