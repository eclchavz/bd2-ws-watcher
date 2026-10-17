from decimal import Decimal

from bd2watcher.cycle import run_check


def by_title(listings):
    return {listing.title: listing for listing in listings}


def test_check_stores_only_watched_sealed_and_supply_listings(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    stored = by_title(store.listings("tcg-corner"))
    assert set(stored) == {
        "Weiss Schwarz Brown Dust 2 Booster Box (Japanese)",
        "Weiss Schwarz Brown Dust 2 Booster Case [x12] (Japanese)",
        "Weiss Schwarz BrownDust2 Trial Deck (Japanese)",
        "Bushiroad Sleeve Collection High-grade Brown Dust 2 Justia",
        "ヴァイスシュヴァルツ ブースターパック ＢｒｏｗｎＤｕｓｔ２ ＢＯＸ",
    }


def test_each_listing_has_price_currency_stock_state_and_kind(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    stored = by_title(store.listings("tcg-corner"))
    box = stored["Weiss Schwarz Brown Dust 2 Booster Box (Japanese)"]
    assert (box.price, box.currency, box.stock_state, box.kind, box.series) == (
        Decimal("54.99"), "USD", "in_stock", "sealed", "Brown Dust 2",
    )
    assert box.url == "https://tcg-corner.com/products/weiss-schwarz-brown-dust-2-booster-box-japanese"
    assert stored["Weiss Schwarz BrownDust2 Trial Deck (Japanese)"].stock_state == "sold_out"
    assert stored["Bushiroad Sleeve Collection High-grade Brown Dust 2 Justia"].kind == "supply"


def test_preorder_is_detected_from_tags(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    case = by_title(store.listings("tcg-corner"))["Weiss Schwarz Brown Dust 2 Booster Case [x12] (Japanese)"]
    assert case.stock_state == "preorder"


def test_full_width_japanese_title_matches_and_any_available_variant_counts(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    jp_box = by_title(store.listings("tcg-corner"))["ヴァイスシュヴァルツ ブースターパック ＢｒｏｗｎＤｕｓｔ２ ＢＯＸ"]
    assert (jp_box.kind, jp_box.stock_state, jp_box.price) == ("sealed", "in_stock", Decimal("56.00"))


def test_single_cards_and_other_series_are_not_stored(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    titles = set(by_title(store.listings("tcg-corner")))
    assert "Brown Dust 2 BD2/W128-P01 Justia (PR) Booster Box Promo" not in titles
    assert "Weiss Schwarz Re:Zero Vol.4 Booster Box (Japanese)" not in titles


def test_a_second_check_updates_listings_instead_of_duplicating(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    assert len(store.listings("tcg-corner")) == 5


def test_lowercase_card_codes_are_still_single_cards(config, store, now, tcg_corner_fetcher):
    run_check(config.source("tcg-corner"), config, tcg_corner_fetcher, store, now)

    assert "Brown Dust 2 bd2/w128-p02 Liatris (PR) Box Topper" not in by_title(store.listings("tcg-corner"))


def test_a_store_that_ignores_paging_does_not_loop_forever(config, store, now):
    from conftest import FIXTURES, FakeFetcher

    class SamePageForever(FakeFetcher):
        def get_json(self, url):
            self.requested.append(url)
            return FakeFetcher.get_json(self.inner, "page-1")

    fetcher = SamePageForever({})
    fetcher.inner = FakeFetcher({"page-1": FIXTURES / "tcg-corner" / "products-page-1.json"})
    run_check(config.source("tcg-corner"), config, fetcher, store, now)

    assert len(fetcher.requested) == 2
    assert len(store.listings("tcg-corner")) == 4


def test_a_failed_check_is_recorded_and_still_raised(config, store, now):
    import pytest
    from conftest import FakeFetcher

    with pytest.raises(KeyError):
        run_check(config.source("tcg-corner"), config, FakeFetcher({}), store, now)

    assert store.last_check("tcg-corner").ok is False
