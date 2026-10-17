from bd2watcher.cli import check_now


def test_check_now_prints_watched_listings_without_saving(config, tcg_corner_fetcher, capsys):
    check_now(config, tcg_corner_fetcher, ["tcg-corner"])

    out = capsys.readouterr().out
    assert "tcg-corner: 5 watched listings" in out
    assert "Weiss Schwarz Brown Dust 2 Booster Box (Japanese)" in out
    assert "54.99 USD" in out and "in_stock" in out
    assert "Re:Zero" not in out
