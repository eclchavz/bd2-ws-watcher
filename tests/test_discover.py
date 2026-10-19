import json

from bd2watcher.cli import capture_fixture, discover
from bd2watcher.config import Source
from bd2watcher.cycle import run_check
from conftest import FakeFetcher


class ShopifySite:
    """A fake Shopify site: robots.txt aside, answers meta.json, collections.json and products.json."""

    def __init__(self, products, robots_blocks=False):
        self.products = products
        self.robots_blocks = robots_blocks

    def get_json(self, url):
        from bd2watcher.fetcher import RobotsDisallowed

        if self.robots_blocks:
            raise RobotsDisallowed(url)
        if url.endswith("/meta.json"):
            return {"name": "Fake Store", "currency": "USD", "domain": "fake.example"}
        if "/collections.json" in url:
            page = int(url.rsplit("page=", 1)[1])
            return {"collections": [
                {"handle": "weiss-schwarz-card-game-1", "title": "Weiss Schwarz"},
                {"handle": "figures", "title": "Figures"},
            ] if page == 1 else []}
        page = int(url.rsplit("page=", 1)[1])
        return {"products": self.products if page == 1 else []}


def fake_source(**kw):
    return Source(name="fake", adapter="shopify", base_url="https://fake.example", currency="USD", **kw)


def test_discover_reports_shopify_currency_collections_and_matches(config, tcg_corner, capsys):
    config.sources[:] = [fake_source()]
    discover(config, ShopifySite(tcg_corner.products), ["fake"])

    out = capsys.readouterr().out
    assert "fake: Shopify" in out
    assert "currency USD" in out
    assert "/collections/weiss-schwarz-card-game-1/products.json" in out
    assert "/collections/figures/" not in out
    assert "4 watched Brown Dust 2 listings" in out


def test_discover_says_when_robots_txt_blocks_a_store(config, capsys):
    config.sources[:] = [fake_source()]
    discover(config, ShopifySite([], robots_blocks=True), ["fake"])

    assert "fake: blocked by robots.txt" in capsys.readouterr().out


def test_discover_says_when_a_store_is_not_shopify(config, capsys):
    class NotShopify:
        def get_json(self, url):
            raise ValueError("not JSON")

    config.sources[:] = [fake_source()]
    discover(config, NotShopify(), ["fake"])

    assert "fake: not Shopify" in capsys.readouterr().out


def test_captured_fixture_replays_in_a_check(config, store, now, tcg_corner, tmp_path):
    config.sources[:] = [fake_source()]
    capture_fixture(config, ShopifySite(tcg_corner.products), "fake", tmp_path)

    pages = sorted(p.name for p in (tmp_path / "fake").iterdir())
    assert pages == ["products-page-1.json", "products-page-2.json"]
    base = "https://fake.example/products.json?limit=250&page="
    replay = FakeFetcher({f"{base}{n}": tmp_path / "fake" / f"products-page-{n}.json" for n in (1, 2)})
    assert len(run_check(config.source("fake"), config, replay, store, now)) == 4


def test_disabled_sources_are_skipped_by_default_but_checkable_by_name(config, tcg_corner, capsys):
    from bd2watcher.cli import check_now

    config.sources[:] = [fake_source(enabled=False)]
    check_now(config, ShopifySite(tcg_corner.products), [])
    assert capsys.readouterr().out == ""
    check_now(config, ShopifySite(tcg_corner.products), ["fake"])
    assert "fake: 4 watched listings" in capsys.readouterr().out


class Recording(ShopifySite):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        return super().get_json(url)


def test_discover_counts_through_the_weiss_schwarz_collection_not_the_whole_catalog(config, tcg_corner, capsys):
    config.sources[:] = [fake_source()]
    site = Recording(tcg_corner.products)
    discover(config, site, ["fake"])

    product_urls = [u for u in site.urls if "products.json" in u]
    assert product_urls and all("/collections/weiss-schwarz-card-game-1/" in u for u in product_urls)


def test_discover_keeps_going_after_an_unknown_name_or_a_broken_store(config, tcg_corner, capsys):
    config.sources[:] = [fake_source()]
    discover(config, ShopifySite(tcg_corner.products), ["nope", "fake"])

    out = capsys.readouterr().out
    assert "nope: no source with that name in config" in out
    assert "fake: Shopify" in out


def test_discover_reports_a_failed_collections_lookup(config, tcg_corner, capsys):
    class NoCollections(ShopifySite):
        def get_json(self, url):
            if "/collections.json" in url:
                raise TimeoutError("timed out")
            return super().get_json(url)

    config.sources[:] = [fake_source()]
    discover(config, NoCollections(tcg_corner.products), ["fake"])
    assert "collections lookup failed: TimeoutError" in capsys.readouterr().out


def test_discover_tells_a_robots_outage_apart_from_a_block(config, capsys):
    from bd2watcher.fetcher import RobotsUnavailable

    class Down:
        def get_json(self, url):
            raise RobotsUnavailable(url)

    config.sources[:] = [fake_source()]
    discover(config, Down(), ["fake"])
    assert "fake: robots.txt is unavailable right now (server error), so try again later" in capsys.readouterr().out


def test_recapturing_replaces_old_pages(config, tcg_corner, tmp_path):
    config.sources[:] = [fake_source()]
    (tmp_path / "fake").mkdir()
    (tmp_path / "fake" / "products-page-3.json").write_text("{}")
    capture_fixture(config, ShopifySite(tcg_corner.products), "fake", tmp_path)

    assert sorted(p.name for p in (tmp_path / "fake").iterdir()) == ["products-page-1.json", "products-page-2.json"]


def test_a_disabled_store_disappears_from_the_dashboard(config, store, now, tcg_corner):
    from fastapi.testclient import TestClient

    from bd2watcher.web import create_app

    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    config.source("tcg-corner").enabled = False
    page = TestClient(create_app(config, store)).get("/").text
    assert "tcg-corner.com/products" not in page
