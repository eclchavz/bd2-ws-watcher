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


def page_with(item_html):
    return f'<html><body><ul class="products"><li class="product">{item_html}</li></ul></body></html>'


def one_listing(config, store, now, html_source, item_html, tmp_path, encoding="utf-8", charset_meta=""):
    path = tmp_path / "p.html"
    path.write_bytes(f"<meta charset='{charset_meta}'>{page_with(item_html)}".encode(encoding))

    class Site:
        requested = []

        def get_text(self, url):
            from bd2watcher.fetcher import decode_html
            return decode_html(path.read_bytes(), None)

    run_check(html_source, config, Site(), store, now)
    return store.listings("html-store")


def test_nested_markup_keeps_spaces_between_words(config, store, now, html_source, tmp_path):
    [listing] = one_listing(config, store, now, html_source,
        '<a href="/p/1"><h2 class="woocommerce-loop-product__title">Brown Dust 2 <span>Booster Box</span></h2></a>'
        '<span class="price"><span class="amount">$50</span></span><p class="stock">In <b>stock</b></p>', tmp_path)
    assert (listing.title, listing.stock_state) == ("Brown Dust 2 Booster Box", "in_stock")


@pytest.mark.parametrize("stock_text", ["Not in stock", "Temporarily not in stock"])
def test_negated_stock_text_is_sold_out(config, store, now, html_source, tmp_path, stock_text):
    [listing] = one_listing(config, store, now, html_source,
        '<a href="/p/1"><h2 class="woocommerce-loop-product__title">Brown Dust 2 Booster Box</h2></a>'
        f'<p class="stock">{stock_text}</p>', tmp_path)
    assert listing.stock_state == "sold_out"


def test_html_preorder_does_not_depend_on_the_shopify_preorder_markers(config, store, now, html_source, tmp_path):
    config.preorder_markers = []
    [listing] = one_listing(config, store, now, html_source,
        '<a href="/p/1"><h2 class="woocommerce-loop-product__title">Brown Dust 2 Booster Box</h2></a>'
        '<p class="stock">予約受付中</p>', tmp_path)
    assert listing.stock_state == "preorder"


def test_a_shift_jis_page_declared_only_in_meta_is_decoded(config, store, now, html_source, tmp_path):
    [listing] = one_listing(config, store, now, html_source,
        '<a href="/p/1"><h2 class="woocommerce-loop-product__title">ブラウンダスト2 ブースターBOX</h2></a>'
        '<p class="stock">在庫切れ</p>', tmp_path, encoding="shift_jis", charset_meta="Shift_JIS")
    assert (listing.title, listing.stock_state) == ("ブラウンダスト2 ブースターBOX", "sold_out")


def test_tracking_parameters_do_not_make_a_product_look_new(config, store, now, html_source, site, notifier):
    from datetime import timedelta

    run_check(html_source, config, site, store, now, [notifier])
    page = FIXTURES / "html-store" / "page-1.html"
    churned = page.read_text().replace('booster-box/"', 'booster-box/?ref=list#top"')
    site.routes["https://shop.example/shop/weiss-schwarz/"] = type("P", (), {"read_text": lambda self, **_: churned})()
    run_check(html_source, config, site, store, now + timedelta(minutes=10), [notifier])
    assert notifier.sent == []


@pytest.mark.parametrize("text, expected", [
    ("$1,014.50", "1014.50"), ("¥5,940", "5940"), ("58,99 €", "58.99"),
    ("1.014,50 €", "1014.50"), ("€1.234", "1234"), ("$12.5", "12.5"),
])
def test_prices_in_common_formats(text, expected):
    from bd2watcher.adapters.html import parse_price
    assert parse_price(text) == Decimal(expected)


def test_discover_does_not_probe_shopify_for_an_html_source(config, html_source, capsys):
    from bd2watcher.discover import discover

    class NoRequests:
        def get_json(self, url):
            raise AssertionError(f"unexpected request {url}")

    discover(config, NoRequests(), ["html-store"])
    assert "html-store: configured for the html adapter" in capsys.readouterr().out
