import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from bd2watcher.config import Source
from bd2watcher.cycle import run_check
from bd2watcher.fx import refresh_rates
from bd2watcher.web import create_app
from conftest import ShopifyStoreFake

BOX = 1001


class FxApi:
    def __init__(self, rates):
        self.rates, self.requested, self.down = rates, [], False

    def get_json(self, url):
        self.requested.append(url)
        if self.down:
            raise OSError("fx api down")
        base = url.split("base=", 1)[1].split("&", 1)[0]
        return {"base": base, "date": "2026-10-17", "rates": {"USD": self.rates[base]}}


def set_price(fake, product_id, price):
    for v in fake.product(product_id)["variants"]:
        v["price"] = price


def test_price_points_are_recorded_only_when_the_price_changes(config, store, notifier, tcg_corner, now):
    source = config.source("tcg-corner")
    run_check(source, config, tcg_corner, store, now, [notifier])
    run_check(source, config, tcg_corner, store, now + timedelta(minutes=10), [notifier])
    set_price(tcg_corner, BOX, "49.99")
    run_check(source, config, tcg_corner, store, now + timedelta(minutes=20), [notifier])

    history = [(p.price, p.at) for p in store.price_history("tcg-corner", str(BOX))]
    assert history == [(Decimal("54.99"), now), (Decimal("49.99"), now + timedelta(minutes=20))]
    assert notifier.sent == []
    assert store.events_of_kind("price_changed") == 1


def test_rates_are_fetched_at_most_once_a_day_and_kept_when_the_api_is_down(config, store, now):
    api = FxApi({"JPY": 0.0067})
    refresh_rates(store, api, {"JPY", "USD"}, now)
    refresh_rates(store, api, {"JPY", "USD"}, now + timedelta(hours=5))
    assert len(api.requested) == 1
    assert store.usd_rate("JPY") == Decimal("0.0067")
    assert store.usd_rate("USD") == Decimal("1")

    api.down = True
    refresh_rates(store, api, {"JPY"}, now + timedelta(days=1))
    assert store.usd_rate("JPY") == Decimal("0.0067")


@pytest.fixture
def jpy_store(config, store, tcg_corner, now):
    """TCG Corner in USD plus a yen store selling the same booster box, with a price change."""
    config.sources.append(Source(name="yen-shop", label="Yen Shop", adapter="shopify",
                                 base_url="https://yen.example", currency="JPY"))
    import copy
    box = copy.deepcopy(tcg_corner.product(BOX))
    box.update(title="Weiss Schwarz Brown Dust 2 Booster Box JP", handle="bd2-box")
    yen = ShopifyStoreFake("https://yen.example", [box])
    set_price(yen, BOX, "5940")
    refresh_rates(store, FxApi({"JPY": 0.0067}), {"JPY", "USD"}, now)
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    run_check(config.source("yen-shop"), config, yen, store, now, [])
    set_price(yen, BOX, "6200")
    run_check(config.source("yen-shop"), config, yen, store, now + timedelta(days=1), [])
    return yen


def test_dashboard_shows_approximate_usd_for_other_currencies(config, store, jpy_store):
    page = TestClient(create_app(config, store)).get("/").text
    row = page.split('data-product="Brown Dust 2 Booster Box (JP)"', 1)[1].split("</tr>", 1)[0]
    assert "6200 JPY" in row and "~$41.54" in row
    assert "/product?name=Brown+Dust+2+Booster+Box+%28JP%29" in row


def test_product_page_charts_one_usd_line_per_store(config, store, jpy_store, now):
    page = TestClient(create_app(config, store)).get("/product", params={"name": "Brown Dust 2 Booster Box (JP)"}).text

    data = json.loads(page.split('<script id="chart-data" type="application/json">', 1)[1].split("</script>", 1)[0])
    series = {d["label"]: d["data"] for d in data["datasets"]}
    assert series["TCG Corner"] == [{"x": now.isoformat(), "y": 54.99}]
    assert series["Yen Shop"] == [{"x": now.isoformat(), "y": 39.8}, {"x": (now + timedelta(days=1)).isoformat(), "y": 41.54}]
    assert '<script src="/static/chart-4.4.1.umd.js">' in page
    script = TestClient(create_app(config, store)).get("/static/chart-4.4.1.umd.js")
    assert script.status_code == 200 and "Chart.js v4.4.1" in script.text


def test_alerts_show_native_and_approximate_usd_price(config, store, now, jpy_store, notifier):
    for v in jpy_store.product(BOX)["variants"]:
        v["available"] = False
    run_check(config.source("yen-shop"), config, jpy_store, store, now + timedelta(days=2), [notifier])
    for v in jpy_store.product(BOX)["variants"]:
        v["available"] = True
    run_check(config.source("yen-shop"), config, jpy_store, store, now + timedelta(days=2, minutes=10), [notifier])

    from bd2watcher.notifiers import format_alert
    assert "6200 JPY (~$41.54)" in format_alert(notifier.sent[0])


def test_product_page_has_a_price_table_for_readers_who_cant_use_the_chart(config, store, jpy_store):
    page = TestClient(create_app(config, store)).get("/product", params={"name": "Brown Dust 2 Booster Box (JP)"}).text
    table = page.split('id="price-table"', 1)[1].split("</table>", 1)[0]
    assert "6200 JPY (~$41.54)" in table and "5940 JPY (~$39.80)" in table and "54.99 USD" in table


def test_a_price_line_continues_to_the_stores_latest_check(config, store, jpy_store, tcg_corner, now):
    later = now + timedelta(days=3)
    run_check(config.source("tcg-corner"), config, tcg_corner, store, later, [])
    page = TestClient(create_app(config, store)).get("/product", params={"name": "Brown Dust 2 Booster Box (JP)"}).text

    data = json.loads(page.split('<script id="chart-data" type="application/json">', 1)[1].split("</script>", 1)[0])
    tcg = next(d["data"] for d in data["datasets"] if d["label"] == "TCG Corner")
    assert tcg == [{"x": now.isoformat(), "y": 54.99}, {"x": later.isoformat(), "y": 54.99}]


def chart(config, store, **params):
    page = TestClient(create_app(config, store)).get("/product", params=params).text
    data = json.loads(page.split('<script id="chart-data" type="application/json">', 1)[1].split("</script>", 1)[0])
    return {d["label"]: d["data"] for d in data["datasets"]}


def test_a_listing_saved_before_price_history_existed_gets_a_starting_point(config, store, tcg_corner, now):
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    store.db.execute("DELETE FROM price_points")  # as if saved by an older version
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now + timedelta(minutes=10), [])

    assert [p.price for p in store.price_history("tcg-corner", str(BOX))] == [Decimal("54.99")]


def test_the_line_stops_at_the_last_successful_check(config, store, tcg_corner, now):
    from conftest import FakeFetcher

    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    with pytest.raises(Exception):
        run_check(config.source("tcg-corner"), config, FakeFetcher({}), store, now + timedelta(days=2), [])
    assert chart(config, store, name="Brown Dust 2 Booster Box (JP)")["TCG Corner"] == [{"x": now.isoformat(), "y": 54.99}]


def test_offers_without_an_exchange_rate_sort_after_converted_ones(config, store, tcg_corner, now):
    import copy
    config.sources.append(Source(name="eur-shop", label="Euro Shop", adapter="shopify",
                                 base_url="https://eur.example", currency="EUR"))
    box = copy.deepcopy(tcg_corner.product(BOX))
    box["variants"][0]["price"] = "1.00"
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    run_check(config.source("eur-shop"), config, ShopifyStoreFake("https://eur.example", [box]), store, now, [])

    page = TestClient(create_app(config, store)).get("/").text
    row = page.split('data-product="Brown Dust 2 Booster Box (JP)"', 1)[1].split("</tr>", 1)[0]
    assert row.index("TCG Corner") < row.index("Euro Shop")


def test_the_product_page_only_shows_its_own_series_and_kind(config, store, now):
    from bd2watcher.models import Listing

    def listing(i, series, kind):
        return Listing("tcg-corner", str(i), f"Item {i}", f"https://x.example/{i}", series, kind,
                       Decimal("10"), "USD", "in_stock", "Booster Box")
    store.save_listings([listing(1, "Brown Dust 2", "sealed"), listing(2, "Other", "sealed")], now)
    for l in store.listings():
        store.add_price_point(l, now)

    page = TestClient(create_app(config, store)).get("/").text
    href = page.split('data-product="Booster Box"', 1)[1].split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
    product = TestClient(create_app(config, store)).get(href).text
    assert "x.example/1" in product and "x.example/2" not in product


def test_each_price_point_converts_with_its_own_currency(config, store, tcg_corner, now):
    refresh_rates(store, FxApi({"JPY": 0.0067}), {"JPY"}, now)
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    store.db.execute("UPDATE price_points SET currency = 'JPY', price = '6000'")  # recorded when the store sold in yen
    assert chart(config, store, name="Brown Dust 2 Booster Box (JP)")["TCG Corner"][0]["y"] == 40.2
