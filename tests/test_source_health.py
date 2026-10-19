from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from bd2watcher.cycle import run_check
from bd2watcher.health import due
from bd2watcher.web import create_app
from conftest import FakeFetcher


def fail(config, store, notifier, at):
    with pytest.raises(Exception):
        run_check(config.source("tcg-corner"), config, FakeFetcher({}), store, at, [notifier])


def test_three_failures_in_a_row_send_one_broken_notice(config, store, notifier, tcg_corner, now):
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [notifier])
    for minutes in (10, 20):
        fail(config, store, notifier, now + timedelta(minutes=minutes))
    assert notifier.sent == []

    fail(config, store, notifier, now + timedelta(minutes=30))
    fail(config, store, notifier, now + timedelta(minutes=40))
    [alert] = notifier.sent
    assert alert.event == "source_broken" and alert.source_label == "TCG Corner" and "KeyError" in alert.error


def test_a_success_after_being_broken_sends_one_recovered_notice(config, store, notifier, tcg_corner, now):
    for minutes in (0, 10, 20):
        fail(config, store, notifier, now + timedelta(minutes=minutes))
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now + timedelta(minutes=30), [notifier])
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now + timedelta(minutes=40), [notifier])

    assert [a.event for a in notifier.sent] == ["source_broken", "source_recovered"]


def test_health_notices_go_to_discord_only(config, store, tcg_corner, now):
    from conftest import RecordingNotifier

    class Email(RecordingNotifier):
        channel = label = "email"

    discord, email = RecordingNotifier(), Email()
    for minutes in (0, 10, 20):
        with pytest.raises(Exception):
            run_check(config.source("tcg-corner"), config, FakeFetcher({}), store, now + timedelta(minutes=minutes),
                      [discord, email])
    assert [a.event for a in discord.sent] == ["source_broken"] and email.sent == []


def test_official_sites_report_health_too(config, store, notifier, now):
    from bd2watcher.official import run_official_check

    for hours in (0, 1, 2):
        with pytest.raises(Exception):
            run_official_check(config.source("official-jp"), config, FakeFetcher({}), store,
                               now + timedelta(hours=hours), [notifier])
    assert [a.event for a in notifier.sent] == ["source_broken"]


@pytest.mark.parametrize("failures, minutes_later, expected", [
    (0, 0, True),     # healthy: the scheduler's interval decides
    (1, 10, True),    # 1 failure: wait 1 interval (10 min)
    (2, 15, False),   # 2 failures: wait 2 intervals
    (2, 20, True),
    (4, 70, False),   # 4 failures: wait 8 intervals (80 min)
    (4, 80, True),
    (9, 119, False),  # capped at 2 hours
    (9, 120, True),
])
def test_failing_sources_back_off_exponentially(config, store, now, failures, minutes_later, expected):
    store.record_check("tcg-corner", now - timedelta(days=1), ok=True, listing_count=4)
    for i in range(failures):
        store.record_check("tcg-corner", now - timedelta(seconds=failures - 1 - i), ok=False, listing_count=0, error="x")
    assert due(config.source("tcg-corner"), config, store, now + timedelta(minutes=minutes_later)) is expected


def test_dashboard_shows_the_failure_count_and_last_error(config, store, notifier, tcg_corner, now):
    run_check(config.source("tcg-corner"), config, tcg_corner, store, now, [notifier])
    for minutes in (10, 20, 30):
        fail(config, store, notifier, now + timedelta(minutes=minutes))

    page = TestClient(create_app(config, store)).get("/").text
    row = page.split('data-source="tcg-corner"', 1)[1].split("</tr>", 1)[0]
    assert "Broken" in row and "3 failed checks in a row" in row and "KeyError" in row
