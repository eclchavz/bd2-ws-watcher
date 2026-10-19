import copy
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from bd2watcher.config import Source
from bd2watcher.cycle import run_check
from bd2watcher.web import create_app
from conftest import ShopifyStoreFake


@pytest.fixture
def two_stores(config, store, tcg_corner, now):
    """TCG Corner from the fixture, plus a second store selling the same booster box for more."""
    config.sources.append(Source(name="japan-figure", label="Japan-Figure", adapter="shopify",
                                 base_url="https://japan-figure.com", currency="USD"))
    box = copy.deepcopy(tcg_corner.product(1001))
    box.update(title="Bushiroad Weiss Schwarz Brown Dust 2 TCG Booster Box", handle="bushiroad-ws-bd2-box")
    box["variants"][0].update(price="61.50", available=False)
    japan_figure = ShopifyStoreFake("https://japan-figure.com", [box])

    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    run_check(config.source("japan-figure"), config, japan_figure, store, now + timedelta(minutes=1), [])
    return TestClient(create_app(config, store))


def test_brown_dust_2_section_groups_each_product_across_stores(two_stores):
    page = two_stores.get("/").text

    box_row = page.split('data-product="Brown Dust 2 Booster Box (JP)"', 1)[1].split("</tr>", 1)[0]
    assert "TCG Corner" in box_row and "Japan-Figure" in box_row
    assert "54.99 USD" in box_row and "61.50 USD" in box_row
    assert "https://japan-figure.com/products/bushiroad-ws-bd2-box" in box_row
    assert "sold out" in box_row and "in stock" in box_row


def test_every_watched_product_has_a_row(two_stores):
    page = two_stores.get("/").text

    for product in ("Brown Dust 2 Booster Box (JP)", "Brown Dust 2 Booster Case (JP)",
                    "Brown Dust 2 Trial Deck (JP)", "Bushiroad Sleeve Collection High-grade Brown Dust 2 Justia"):
        assert f'data-product="{product}"' in page


def test_sources_section_shows_last_check_and_health(config, store, two_stores, now):
    from conftest import FakeFetcher

    with pytest.raises(KeyError):
        run_check(config.source("japan-figure"), config, FakeFetcher({}), store, now + timedelta(minutes=5), [])

    page = two_stores.get("/").text
    sources = page.split('id="sources"', 1)[1]
    tcg = sources.split('data-source="tcg-corner"', 1)[1].split("</tr>", 1)[0]
    jf = sources.split('data-source="japan-figure"', 1)[1].split("</tr>", 1)[0]
    assert "OK" in tcg and "2026-10-17" in tcg
    assert "Failing" in jf and "KeyError" in jf


def test_dashboard_is_read_only(two_stores):
    assert two_stores.post("/").status_code == 405


def test_a_database_from_before_the_dashboard_is_upgraded_in_place(config, tcg_corner, now, tmp_path):
    import sqlite3

    from bd2watcher.store import Store

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE listings (source TEXT NOT NULL, external_id TEXT NOT NULL, title TEXT NOT NULL,
            url TEXT NOT NULL, series TEXT NOT NULL, kind TEXT NOT NULL, price TEXT, currency TEXT NOT NULL,
            stock_state TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
            PRIMARY KEY (source, external_id));
        CREATE TABLE events (id INTEGER PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
            kind TEXT NOT NULL, at TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, series TEXT NOT NULL,
            listing_kind TEXT NOT NULL, price TEXT, currency TEXT NOT NULL, stock_state TEXT NOT NULL);
    """)
    old.close()

    store = Store(str(path))
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    assert "Brown Dust 2 Booster Box (JP)" in {l.product for l in store.listings()}


def test_last_check_time_is_shown_in_the_configured_time_zone(two_stores, monkeypatch):
    monkeypatch.setenv("TZ", "America/Phoenix")
    page = two_stores.get("/").text
    tcg = page.split('data-source="tcg-corner"', 1)[1].split("</tr>", 1)[0]
    assert "2026-10-17 05:00 MST" in tcg


def test_offers_with_unknown_price_sort_after_priced_ones(config, store, now):
    from bd2watcher.models import Listing
    from bd2watcher.web import create_app

    def offer(name, price):
        return Listing("tcg-corner", name, "Box", f"https://{name}.example", "Brown Dust 2", "sealed",
                       price, "USD", "in_stock", "Brown Dust 2 Booster Box (JP)")

    from decimal import Decimal
    store.save_listings([offer("a-unknown", None), offer("b-priced", Decimal("50"))], now)
    page = TestClient(create_app(config, store)).get("/").text
    assert page.index("b-priced.example") < page.index("a-unknown.example")
