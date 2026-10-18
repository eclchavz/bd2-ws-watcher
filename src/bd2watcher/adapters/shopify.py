from decimal import Decimal

from bd2watcher.config import Source
from bd2watcher.models import RawListing

PAGE_SIZE = 250
MAX_PAGES = 40


def fetch(source: Source, fetcher) -> list[RawListing]:
    """Read every page of a Shopify store's products.json until an empty page comes back.

    Stops early if a page repeats products already seen, which happens when a store ignores `page`.
    """
    listings: list[RawListing] = []
    seen_ids: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{source.base_url}{source.products_path}?limit={PAGE_SIZE}&page={page}"
        products = fetcher.get_json(url).get("products", [])
        new = [p for p in products if str(p["id"]) not in seen_ids]
        if not new:
            break
        seen_ids.update(str(p["id"]) for p in new)
        listings.extend(_to_raw(source, p) for p in new)
    return listings


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
