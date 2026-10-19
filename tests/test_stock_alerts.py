import copy
from decimal import Decimal
from datetime import timedelta

from bd2watcher.cycle import run_check

BOX = 1001         # Brown Dust 2 Booster Box, in stock
TRIAL_DECK = 1003  # Brown Dust 2 Trial Deck, sold out


def check(config, store, notifier, fake, at):
    run_check(config.source("tcg-corner"), config, fake, store, at, [notifier])


def set_available(fake, product_id, available):
    for variant in fake.product(product_id)["variants"]:
        variant["available"] = available


def kinds(notifier):
    return [(a.event, a.listing.title) for a in notifier.sent]


def test_first_check_is_a_silent_baseline(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)

    assert notifier.sent == []
    assert len(store.listings("tcg-corner")) == 4


def test_sold_out_to_in_stock_sends_one_restock_alert(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    set_available(tcg_corner, TRIAL_DECK, True)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))

    assert kinds(notifier) == [("restock", "Weiss Schwarz BrownDust2 Trial Deck (Japanese)")]
    alert = notifier.sent[0]
    assert (alert.listing.price, alert.listing.currency, alert.listing.stock_state) == (
        Decimal("14.99"), "USD", "in_stock",
    )
    assert alert.listing.url == "https://tcg-corner.com/products/weiss-schwarz-browndust2-trial-deck-japanese"


def test_new_watched_listing_sends_new_listing_alert(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    new_box = copy.deepcopy(tcg_corner.product(BOX))
    new_box.update(id=2001, title="Weiss Schwarz Brown Dust 2 Vol.2 Booster Box (Japanese)", handle="bd2-vol2-box")
    tcg_corner.products.append(new_box)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))

    assert kinds(notifier) == [("new_listing", "Weiss Schwarz Brown Dust 2 Vol.2 Booster Box (Japanese)")]


def test_listing_turning_to_preorder_sends_preorder_opened(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    set_available(tcg_corner, TRIAL_DECK, True)
    tcg_corner.product(TRIAL_DECK)["tags"].append("Pre-Order")
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))

    assert kinds(notifier) == [("preorder_opened", "Weiss Schwarz BrownDust2 Trial Deck (Japanese)")]


def test_a_listing_that_stays_in_stock_sends_nothing_again(config, store, notifier, tcg_corner, now):
    for minutes in (0, 10, 20, 30):
        check(config, store, notifier, tcg_corner, now + timedelta(minutes=minutes))

    assert notifier.sent == []


def test_flapping_stock_alerts_at_most_once_per_six_hours(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    t = now
    for _ in range(4):  # four sold-out -> in-stock flips within six hours
        t += timedelta(minutes=30)
        set_available(tcg_corner, TRIAL_DECK, True)
        check(config, store, notifier, tcg_corner, t)
        t += timedelta(minutes=30)
        set_available(tcg_corner, TRIAL_DECK, False)
        check(config, store, notifier, tcg_corner, t)
    assert len(notifier.sent) == 1

    set_available(tcg_corner, TRIAL_DECK, True)
    check(config, store, notifier, tcg_corner, now + timedelta(hours=6, minutes=31))
    assert len(notifier.sent) == 2


def test_listing_missing_from_a_check_is_sold_out_and_alerts_when_it_returns(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    box = tcg_corner.product(BOX)
    tcg_corner.products.remove(box)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))

    stored = {l.external_id: l for l in store.listings("tcg-corner")}
    assert stored[str(BOX)].stock_state == "sold_out"
    assert notifier.sent == []

    tcg_corner.products.append(box)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=20))
    assert kinds(notifier) == [("restock", "Weiss Schwarz Brown Dust 2 Booster Box (Japanese)")]


def test_every_event_and_alert_is_recorded(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    set_available(tcg_corner, TRIAL_DECK, True)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))

    assert [(a.event, a.channel) for a in store.alerts()] == [("restock", "discord")]


def test_preorder_becoming_in_stock_alerts(config, store, notifier, tcg_corner, now):
    case = 1002  # on preorder in the fixture
    check(config, store, notifier, tcg_corner, now)
    tcg_corner.product(case)["tags"].remove("Pre-Order")
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))

    assert kinds(notifier) == [("restock", "Weiss Schwarz Brown Dust 2 Booster Case [x12] (Japanese)")]


def test_cooldown_is_per_event_kind_so_a_new_listing_does_not_hide_its_restock(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    new_box = copy.deepcopy(tcg_corner.product(BOX))
    new_box.update(id=2001, title="Weiss Schwarz Brown Dust 2 Vol.2 Booster Box (Japanese)", handle="bd2-vol2-box")
    tcg_corner.products.append(new_box)
    set_available(tcg_corner, 2001, False)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))
    set_available(tcg_corner, 2001, True)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=20))

    assert [k for k, _ in kinds(notifier)] == ["new_listing", "restock"]


def test_an_empty_result_after_listings_is_a_failed_check_not_a_sell_out(config, store, notifier, tcg_corner, now):
    import pytest

    check(config, store, notifier, tcg_corner, now)
    everything = list(tcg_corner.products)
    tcg_corner.products.clear()
    with pytest.raises(Exception):
        check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))
    assert store.last_check("tcg-corner").ok is False
    assert {l.stock_state for l in store.listings("tcg-corner")} != {"sold_out"}

    tcg_corner.products.extend(everything)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=20))
    assert notifier.sent == []


def test_alert_history_keeps_the_listing_as_it_was_when_alerted(config, store, notifier, tcg_corner, now):
    check(config, store, notifier, tcg_corner, now)
    set_available(tcg_corner, TRIAL_DECK, True)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=10))
    set_available(tcg_corner, TRIAL_DECK, False)
    check(config, store, notifier, tcg_corner, now + timedelta(minutes=20))

    assert store.alerts()[0].listing.stock_state == "in_stock"
