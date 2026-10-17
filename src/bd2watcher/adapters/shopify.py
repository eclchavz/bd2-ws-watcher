from decimal import Decimal

from bd2watcher.config import Source
from bd2watcher.models import RawListing

PAGE_SIZE = 250


def fetch(source: Source, fetcher) -> list[RawListing]:
    """Read every page of a Shopify store's products.json until an empty page comes back."""
    listings: list[RawListing] = []
    page = 1
    while True:
        url = f"{source.base_url}{source.products_path}?limit={PAGE_SIZE}&page={page}"
        products = fetcher.get_json(url).get("products", [])
        if not products:
            return listings
        listings.extend(_to_raw(source, p) for p in products)
        page += 1


def _to_raw(source: Source, product: dict) -> RawListing:
    variants = product.get("variants", [])
    prices = [Decimal(v["price"]) for v in variants if v.get("price") is not None]
    available = [v["available"] for v in variants if "available" in v]
    tags = product.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return RawListing(
        external_id=str(product["id"]),
        title=product["title"],
        url=f"{source.base_url}/products/{product['handle']}",
        price=min(prices) if prices else None,
        available=any(available) if available else None,
        product_type=product.get("product_type", ""),
        tags=tuple(tags),
    )
