from collections.abc import Iterator
from decimal import Decimal

from bd2watcher.config import Source
from bd2watcher.models import RawListing

PAGE_SIZE = 250
MAX_PAGES = 40


def pages(source: Source, fetcher) -> Iterator[tuple[int, dict]]:
    """Yield (page number, products.json body) until a page with no new products, which is yielded too.

    Stops early if a page only repeats products already seen, which happens when a store ignores `page`.
    """
    seen_ids: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        url = f"{source.base_url}{source.products_path}?limit={PAGE_SIZE}&page={page}"
        body = fetcher.get_json(url)
        yield page, body
        new_ids = {str(p["id"]) for p in body.get("products", [])} - seen_ids
        if not new_ids:
            return
        seen_ids |= new_ids


def fetch(source: Source, fetcher) -> list[RawListing]:
    """Read every page of a Shopify store's products.json."""
    listings: dict[str, RawListing] = {}
    for _, body in pages(source, fetcher):
        for product in body.get("products", []):
            listings.setdefault(str(product["id"]), _to_raw(source, product))
    return list(listings.values())


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
