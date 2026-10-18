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
        "**🟢 RESTOCK** · Weiss Schwarz BrownDust2 Trial Deck (Japanese)\n"
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

    assert [(a.event, a.channel) for a in store.alerts()] == [("restock", "dry-run")]
    assert "RESTOCK" in caplog.text
