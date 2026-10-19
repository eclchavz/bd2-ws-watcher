from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from bd2watcher.official import run_official_check
from bd2watcher.web import create_app
from conftest import FIXTURES

JP = FIXTURES / "official-jp" / "products.html"
EN = FIXTURES / "official-en" / "products.html"

NEW_BD2_PRODUCT = """<li><a href="/products/brd_eb/">エクストラブースター ブラウンダスト2 Vol.2</a><p>2026年12月11日（金）発売</p></li>"""
NEW_OTHER_SET = """<li><a href="/products/osk_bp/">ブースターパック 【推しの子】 Vol.3</a><p>2026年11月13日（金）発売</p></li>"""
NEW_EN_BD2 = """<article><a href="/products/brd_bp_en/"><h3>Booster Pack BrownDust2</h3></a><span>Release: Feb 19, 2027</span></article>"""


class Site:
    def __init__(self, base, page):
        self.base, self.html = base, page.read_text(encoding="utf-8")
        self.requested = []

    def get_text(self, url):
        self.requested.append(url)
        assert url == f"{self.base}/products/"
        return self.html

    def add(self, item):
        for closing in ("</ul>", "</div>"):
            if closing in self.html:
                self.html = self.html.replace(closing, item + closing, 1)
                return


@pytest.fixture
def jp_site():
    return Site("https://ws-tcg.com", JP)


@pytest.fixture
def en_site():
    return Site("https://en.ws-tcg.com", EN)


def check(config, name, site, store, at, notifier):
    run_official_check(config.source(name), config, site, store, at, [notifier])


def test_first_official_check_is_a_silent_baseline(config, store, now, jp_site, notifier):
    check(config, "official-jp", jp_site, store, now, notifier)

    assert notifier.sent == []
    assert store.digest_queue() == []
    assert {s.set_id for s in store.sets()} == {"brd_bp", "brd_td", "rz_bp4"}


def test_a_new_brown_dust_2_product_alerts_immediately(config, store, now, jp_site, notifier):
    check(config, "official-jp", jp_site, store, now, notifier)
    jp_site.add(NEW_BD2_PRODUCT)
    check(config, "official-jp", jp_site, store, now + timedelta(hours=1), notifier)

    [alert] = notifier.sent
    assert alert.event == "new_set"
    assert (alert.announcement.title, alert.announcement.release_date, alert.announcement.url) == (
        "エクストラブースター ブラウンダスト2 Vol.2", date(2026, 12, 11), "https://ws-tcg.com/products/brd_eb/")
    assert store.digest_queue() == []


def test_a_new_set_from_another_series_waits_for_the_digest(config, store, now, jp_site, notifier):
    check(config, "official-jp", jp_site, store, now, notifier)
    jp_site.add(NEW_OTHER_SET)
    check(config, "official-jp", jp_site, store, now + timedelta(hours=1), notifier)

    assert notifier.sent == []
    assert [s.title for s in store.digest_queue()] == ["ブースターパック 【推しの子】 Vol.3"]


def test_japanese_and_english_dates_and_set_codes_are_read(config, store, now, jp_site, en_site, notifier):
    check(config, "official-jp", jp_site, store, now, notifier)
    check(config, "official-en", en_site, store, now, notifier)

    sets = {(s.source, s.set_id): s for s in store.sets()}
    assert sets[("official-jp", "brd_bp")].release_date == date(2026, 7, 3)
    assert sets[("official-jp", "brd_bp")].series == "Brown Dust 2"
    assert sets[("official-jp", "rz_bp4")].series == ""
    assert sets[("official-en", "rz_bp4")].release_date == date(2026, 10, 30)
    assert sets[("official-en", "fr_bp")].release_date == date(2026, 12, 4)
    assert sets[("official-en", "fr_bp")].language == "EN"


def test_an_english_brown_dust_2_announcement_has_its_own_alert(config, store, now, en_site, notifier):
    check(config, "official-en", en_site, store, now, notifier)
    en_site.add(NEW_EN_BD2)
    check(config, "official-en", en_site, store, now + timedelta(hours=1), notifier)

    assert [(a.event, a.announcement.title) for a in notifier.sent] == [("english_release", "Booster Pack BrownDust2")]
    from bd2watcher.notifiers import format_alert
    assert "ENGLISH" in format_alert(notifier.sent[0])


def test_other_new_english_sets_wait_for_the_digest(config, store, now, en_site, notifier):
    check(config, "official-en", en_site, store, now, notifier)
    en_site.add('<article><a href="/products/osk_bp_en/"><h3>Booster Pack Oshi no Ko</h3></a></article>')
    check(config, "official-en", en_site, store, now + timedelta(hours=1), notifier)

    assert notifier.sent == []
    assert [s.title for s in store.digest_queue()] == ["Booster Pack Oshi no Ko"]


def test_an_official_page_with_no_products_is_a_failed_check(config, store, now, jp_site, notifier):
    check(config, "official-jp", jp_site, store, now, notifier)
    jp_site.html = "<html><body>maintenance</body></html>"
    with pytest.raises(Exception):
        check(config, "official-jp", jp_site, store, now + timedelta(hours=1), notifier)
    assert store.last_check("official-jp").ok is False


def test_dashboard_lists_sets_by_language_with_dates_and_store_links(config, store, now, jp_site, en_site,
                                                                      notifier, tcg_corner):
    from bd2watcher.cycle import run_check

    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [])
    check(config, "official-jp", jp_site, store, now, notifier)
    check(config, "official-en", en_site, store, now, notifier)
    page = TestClient(create_app(config, store)).get("/").text

    sets = page.split('id="sets"', 1)[1]
    brd = sets.split('data-set="official-jp/brd_bp"', 1)[1].split("</tr>", 1)[0]
    assert "ブースターパック ブラウンダスト2" in brd and "2026-07-03" in brd and "JP" in brd
    assert 'href="#watched"' in brd  # Brown Dust 2 has store listings above
    fr = sets.split('data-set="official-en/fr_bp"', 1)[1].split("</tr>", 1)[0]
    assert "EN" in fr and "2026-12-04" in fr and 'href="#watched"' not in fr


def test_a_store_without_a_currency_is_rejected():
    from bd2watcher.config import Source

    with pytest.raises(ValueError):
        Source(name="x", adapter="shopify", base_url="https://x.example")


def test_capture_fixture_saves_the_official_list_page(config, jp_site, tmp_path):
    from bd2watcher.discover import capture_fixture

    capture_fixture(config, jp_site, "official-jp", tmp_path)
    assert (tmp_path / "official-jp" / "products.html").read_text(encoding="utf-8") == jp_site.html
