from decimal import Decimal

import pytest

from bd2watcher.config import HtmlSelectors, Source
from bd2watcher.cycle import run_check
from conftest import FIXTURES


class HtmlSite:
    def __init__(self, routes):
        self.routes = routes
        self.requested = []

    def get_text(self, url):
        self.requested.append(url)
        return self.routes[url].read_text(encoding="utf-8")


@pytest.fixture
def html_source(config):
    source = Source(
        name="html-store", label="HTML Store", adapter="html", base_url="https://shop.example", currency="USD",
        html=HtmlSelectors(
            list_path="/shop/weiss-schwarz/",
            product="li.product", title=".woocommerce-loop-product__title", link="a", price=".price .amount",
            stock=".stock", next_page="a.next",
        ),
    )
    config.sources.append(source)
    return source


@pytest.fixture
def site():
    return HtmlSite({
        "https://shop.example/shop/weiss-schwarz/": FIXTURES / "html-store" / "page-1.html",
        "https://shop.example/shop/weiss-schwarz/page/2/": FIXTURES / "html-store" / "page-2.html",
    })


def test_html_store_listings_come_from_config_selectors_across_pages(config, store, now, html_source, site):
    run_check(html_source, config, site, store, now)

    stored = {l.title: l for l in store.listings("html-store")}
    assert {t: (l.price, l.stock_state, l.url) for t, l in stored.items()} == {
        "Weiss Schwarz Brown Dust 2 Booster Box (Japanese)": (
            Decimal("58.99"), "in_stock", "https://shop.example/product/weiss-schwarz-brown-dust-2-booster-box/"),
        "Weiss Schwarz Brown Dust 2 Trial Deck": (
            Decimal("1014.50"), "sold_out", "https://shop.example/product/weiss-schwarz-brown-dust-2-trial-deck/"),
        "Brown Dust 2 Booster Case (12 boxes)": (
            Decimal("680.00"), "preorder", "https://shop.example/product/bd2-case/"),
        "Bushiroad Rubber Playmat Brown Dust 2": (
            Decimal("24.00"), "unknown", "https://shop.example/product/bd2-playmat/"),
        "Bushiroad Deck Case Brown Dust 2": (
            Decimal("12.00"), "sold_out", "https://shop.example/product/bd2-deck-case/"),
    }


def test_html_paging_never_requests_the_same_page_twice(config, store, now, html_source):
    loop = HtmlSite({"https://shop.example/shop/weiss-schwarz/": FIXTURES / "html-store" / "page-1.html",
                     "https://shop.example/shop/weiss-schwarz/page/2/": FIXTURES / "html-store" / "page-1.html"})
    run_check(html_source, config, loop, store, now)
    assert len(loop.requested) == 2


def test_an_html_source_needs_selectors():
    with pytest.raises(ValueError):
        Source(name="x", adapter="html", base_url="https://x.example", currency="USD")
