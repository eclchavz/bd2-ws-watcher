import re
from collections.abc import Iterator
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from bd2watcher.classify import normalise
from bd2watcher.config import Source
from bd2watcher.models import RawListing


def pages(source: Source, fetcher) -> Iterator[tuple[int, str, str]]:
    """Yield (page number, url, html), following the next-page link until there isn't one or it repeats."""
    sel = source.html
    url, seen = urljoin(source.base_url, sel.list_path), set()
    for page in range(1, sel.max_pages + 1):
        if url in seen:
            return
        seen.add(url)
        text = fetcher.get_text(url)
        yield page, url, text
        next_link = HTMLParser(text).css_first(sel.next_page) if sel.next_page else None
        if next_link is None or not next_link.attributes.get("href"):
            return
        url = urljoin(url, next_link.attributes["href"])


def fetch(source: Source, fetcher) -> list[RawListing]:
    listings: dict[str, RawListing] = {}
    for _, url, text in pages(source, fetcher):
        for raw in parse(source, url, text):
            listings.setdefault(raw.external_id, raw)
    return list(listings.values())


def parse(source: Source, page_url: str, text: str) -> list[RawListing]:
    sel = source.html
    found = []
    for node in HTMLParser(text).css(sel.product):
        title, link = node.css_first(sel.title), node.css_first(sel.link)
        if title is None or link is None or not link.attributes.get("href"):
            continue
        price = node.css_first(sel.price) if sel.price else None
        stock = node.css_first(sel.stock) if sel.stock else None
        state = stock_state(stock.text(strip=True) if stock else "", source)
        url = urljoin(page_url, link.attributes["href"])
        found.append(RawListing(
            external_id=url, title=title.text(strip=True), url=url,
            price=parse_price(price.text(strip=True)) if price else None,
            available={"in_stock": True, "preorder": True, "sold_out": False}.get(state),
            product_type="", tags=("pre-order",) if state == "preorder" else (),
        ))
    return found


def stock_state(text: str, source: Source) -> str:
    """Map a store's stock text to a stock state using the source's patterns. Sold out wins, then preorder."""
    folded = normalise(text)
    for state, patterns in (("sold_out", source.html.sold_out), ("preorder", source.html.preorder),
                            ("in_stock", source.html.in_stock)):
        if any(normalise(p) in folded for p in patterns):
            return state
    return "unknown"


def parse_price(text: str) -> Decimal | None:
    """'$1,014.50' -> 1014.50, '¥5,940' -> 5940, '58,99 €' -> 58.99."""
    match = re.search(r"\d[\d.,]*", normalise(text))
    if not match:
        return None
    number = match.group().rstrip(".,")
    if "," in number and "." in number:
        number = number.replace(",", "")
    elif re.fullmatch(r"\d+,\d{2}", number):
        number = number.replace(",", ".")
    else:
        number = number.replace(",", "")
    try:
        return Decimal(number)
    except InvalidOperation:
        return None
