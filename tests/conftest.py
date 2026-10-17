import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bd2watcher.config import load_config
from bd2watcher.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = Path(__file__).parent.parent / "config" / "config.yaml"


class FakeFetcher:
    """Serves fixture files by URL, so tests never touch the network."""

    def __init__(self, routes: dict[str, Path]):
        self.routes = routes
        self.requested: list[str] = []

    def get_json(self, url: str):
        self.requested.append(url)
        return json.loads(self.routes[url].read_text(encoding="utf-8"))


@pytest.fixture
def config():
    return load_config(CONFIG)


@pytest.fixture
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture
def now():
    return datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def tcg_corner_fetcher():
    base = "https://tcg-corner.com/products.json?limit=250&page="
    return FakeFetcher(
        {f"{base}{n}": FIXTURES / "tcg-corner" / f"products-page-{n}.json" for n in (1, 2, 3)}
    )
