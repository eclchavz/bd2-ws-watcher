import json
from datetime import timedelta

import httpx

from bd2watcher.cycle import run_check
from bd2watcher.notifiers import DiscordNotifier, DryRunNotifier

TRIAL_DECK = 1003
WEBHOOK = "https://discord.example/api/webhooks/1/token"


def discord(status, posted):
    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        return httpx.Response(status)

    return DiscordNotifier(WEBHOOK, transport=httpx.MockTransport(handler))


def restock_trial_deck(config, store, tcg_corner, now, notifiers):
    source = config.source("tcg-corner")
    run_check(source, config, tcg_corner, store, now, notifiers)
    for v in tcg_corner.product(TRIAL_DECK)["variants"]:
        v["available"] = True
    run_check(source, config, tcg_corner, store, now + timedelta(minutes=10), notifiers)


def test_discord_message_has_title_store_price_stock_and_link_and_pings_nobody(config, store, tcg_corner, now):
    posted = []
    restock_trial_deck(config, store, tcg_corner, now, [discord(204, posted)])

    assert [str(r.url) for r in posted] == [WEBHOOK]
    body = json.loads(posted[0].content)
    assert body["content"] == (
        "**🟢 IN STOCK** · Weiss Schwarz BrownDust2 Trial Deck (Japanese)\n"
        "TCG Corner · 14.99 USD · in stock\n"
        "https://tcg-corner.com/products/weiss-schwarz-browndust2-trial-deck-japanese"
    )
    assert body["allowed_mentions"] == {"parse": []}


def test_a_failed_discord_send_is_recorded_and_does_not_break_the_check(config, store, tcg_corner, now):
    restock_trial_deck(config, store, tcg_corner, now, [discord(500, [])])

    assert store.last_check("tcg-corner").ok is True
    assert store.last_alert_at("tcg-corner", str(TRIAL_DECK)) is None  # a failed send doesn't start the cooldown


def test_dry_run_records_the_alert_as_dry_run_and_sends_nothing(config, store, tcg_corner, now, caplog):
    caplog.set_level("INFO")
    restock_trial_deck(config, store, tcg_corner, now, [DryRunNotifier("discord")])

    assert [(a.event, a.channel) for a in store.alerts()] == [("restock", "dry-run discord")]
    assert "IN STOCK" in caplog.text


def test_a_failed_send_is_retried_on_the_next_check(config, store, tcg_corner, now):
    posted = []
    responses = iter([500, 204])

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        return httpx.Response(next(responses))

    notifiers = [DiscordNotifier(WEBHOOK, transport=httpx.MockTransport(handler))]
    restock_trial_deck(config, store, tcg_corner, now, notifiers)
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now + timedelta(minutes=20), notifiers)

    assert len(posted) == 2
    assert [(a.event, a.channel) for a in store.alerts() if a.ok] == [("restock", "discord")]


def test_run_refuses_to_start_without_a_webhook_unless_dry_run(config, monkeypatch):
    import pytest

    from bd2watcher.cli import build_notifiers

    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    with pytest.raises(SystemExit):
        build_notifiers(config, dry_run=False)
    assert [n.label for n in build_notifiers(config, dry_run=True)] == ["dry-run discord"]


def test_dry_run_flag_works_after_the_subcommand(monkeypatch):
    import sys

    from bd2watcher import cli

    seen = {}
    monkeypatch.setattr(sys, "argv", ["bd2watcher", "send-test-alert", "discord", "--dry-run"])
    monkeypatch.setattr(cli, "send_test_alert", lambda notifiers, channel: seen.update(labels=[n.label for n in notifiers]))
    cli.main()
    assert seen["labels"] == ["dry-run discord"]
