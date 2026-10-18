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


class RecordingNotifier:
    """Stands in for Discord: keeps every alert it was asked to send."""

    channel = label = "discord"

    def __init__(self):
        self.sent = []

    def send(self, alert) -> None:
        self.sent.append(alert)


class ShopifyStoreFake:
    """A fake Shopify store whose products a test can change between checks."""

    def __init__(self, base_url: str, products: list[dict]):
        self.base_url = base_url
        self.products = products
        self.requested: list[str] = []

    def get_json(self, url: str):
        self.requested.append(url)
        page = int(url.rsplit("page=", 1)[1])
        return {"products": self.products if page == 1 else []}

    def product(self, product_id: int) -> dict:
        return next(p for p in self.products if p["id"] == product_id)


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def tcg_corner():
    products = json.loads((FIXTURES / "tcg-corner" / "products-page-1.json").read_text(encoding="utf-8"))
    return ShopifyStoreFake("https://tcg-corner.com", products["products"])
