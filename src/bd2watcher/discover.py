import json
from pathlib import Path

from bd2watcher.adapters import shopify
from bd2watcher.classify import normalise
from bd2watcher.config import Config, Source
from bd2watcher.cycle import find_watched
from bd2watcher.fetcher import RobotsDisallowed

COLLECTION_HINTS = ("weiss", "ヴァイス", "ws-tcg", "brown dust", "browndust")
MAX_COLLECTION_PAGES = 10


def discover(config: Config, fetcher, source_names: list[str]) -> None:
    """Report, for each store, whether it's Shopify, its currency, Weiss Schwarz collections and BD2 matches."""
    for name in source_names or [s.name for s in config.sources]:
        source = config.source(name)
        try:
            meta = fetcher.get_json(f"{source.base_url}/meta.json")
        except RobotsDisallowed:
            print(f"{name}: blocked by robots.txt, so it can't be checked politely")
            continue
        except Exception as e:
            print(f"{name}: not Shopify, or unreachable ({type(e).__name__}: {e}). Use the html adapter (ticket 05).")
            continue

        print(f"{name}: Shopify ({meta.get('name', '?')}), currency {meta.get('currency', '?')}")
        for handle, title in _ws_collections(source, fetcher):
            print(f"  collection {title!r}: products_path: /collections/{handle}/products.json")
        try:
            print(f"  {len(find_watched(source, config, fetcher))} watched Brown Dust 2 listings"
                  f" via {source.products_path}")
        except Exception as e:
            print(f"  products check failed: {type(e).__name__}: {e}")


def _ws_collections(source: Source, fetcher) -> list[tuple[str, str]]:
    found = []
    for page in range(1, MAX_COLLECTION_PAGES + 1):
        try:
            collections = fetcher.get_json(f"{source.base_url}/collections.json?limit=250&page={page}")["collections"]
        except Exception:
            break
        if not collections:
            break
        for c in collections:
            text = normalise(f"{c.get('handle', '')} {c.get('title', '')}")
            if any(normalise(h) in text for h in COLLECTION_HINTS):
                found.append((c["handle"], c.get("title", c["handle"])))
    return found


def capture_fixture(config: Config, fetcher, name: str, out_dir: Path) -> None:
    """Save a store's current products.json pages so tests can replay them."""
    source = config.source(name)
    target = Path(out_dir) / name
    target.mkdir(parents=True, exist_ok=True)
    for page, body in shopify.pages(source, fetcher):
        path = target / f"products-page-{page}.json"
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {path}")
