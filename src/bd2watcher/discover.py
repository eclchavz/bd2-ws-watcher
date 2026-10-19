import json
import shutil
import tempfile
from pathlib import Path

from bd2watcher.adapters import html, shopify
from bd2watcher.classify import normalise
from bd2watcher.config import Config, Source
from bd2watcher.cycle import watched
from bd2watcher.fetcher import RobotsDisallowed, RobotsUnavailable

COLLECTION_HINTS = ("weiss", "ヴァイス", "ws-tcg", "brown dust", "browndust")
MAX_COLLECTION_PAGES = 10
DISCOVER_PRODUCT_PAGES = 4  # enough to spot Brown Dust 2 without crawling a whole catalog


def discover(config: Config, fetcher, source_names: list[str]) -> None:
    """Report, for each store, whether it's Shopify, its currency, Weiss Schwarz collections and BD2 matches."""
    for name in source_names or [s.name for s in config.sources]:
        try:
            _discover_one(config, fetcher, config.source(name))
        except KeyError:
            print(f"{name}: no source with that name in config")
        except Exception as e:
            print(f"{name}: discover failed ({type(e).__name__}: {e})")


def _discover_one(config: Config, fetcher, source: Source) -> None:
    name = source.name
    if source.adapter == "html":
        print(f"{name}: configured for the html adapter, so try `bd2watcher check-now {name}`")
        return
    try:
        meta = fetcher.get_json(f"{source.base_url}/meta.json")
    except RobotsUnavailable:
        print(f"{name}: robots.txt is unavailable right now (server error), so try again later")
        return
    except RobotsDisallowed:
        print(f"{name}: blocked by robots.txt, so it can't be checked politely")
        return
    except Exception as e:
        print(f"{name}: not Shopify, or unreachable ({type(e).__name__}: {e}). Use the html adapter (ticket 05).")
        return

    print(f"{name}: Shopify ({meta.get('name', '?')}), currency {meta.get('currency', '?')}")
    try:
        collections = _ws_collections(source, fetcher)
    except Exception as e:
        print(f"  collections lookup failed: {type(e).__name__}: {e}")
        collections = []
    for handle, title in collections:
        print(f"  collection {title!r}: products_path: /collections/{handle}/products.json")

    path = f"/collections/{collections[0][0]}/products.json" if collections else source.products_path
    probe = source.model_copy(update={"products_path": path})
    raws = [shopify._to_raw(probe, p) for _, body in shopify.pages(probe, fetcher, DISCOVER_PRODUCT_PAGES)
            for p in body.get("products", [])]
    print(f"  {len(watched(probe, config, raws))} watched Brown Dust 2 listings via {path}"
          f" (first {DISCOVER_PRODUCT_PAGES} pages at most)")


def _ws_collections(source: Source, fetcher) -> list[tuple[str, str]]:
    found, seen = [], set()
    for page in range(1, MAX_COLLECTION_PAGES + 1):
        collections = fetcher.get_json(f"{source.base_url}/collections.json?limit=250&page={page}")["collections"]
        new = [c for c in collections if c.get("handle") and c["handle"] not in seen]
        if not new:
            break
        for c in new:
            seen.add(c["handle"])
            if any(normalise(h) in normalise(f"{c['handle']} {c.get('title', '')}") for h in COLLECTION_HINTS):
                found.append((c["handle"], c.get("title", c["handle"])))
    return found


def capture_fixture(config: Config, fetcher, name: str, out_dir: Path) -> None:
    """Save a store's current pages (products.json, or html) so tests can replay them, replacing any earlier capture."""
    source = config.source(name)
    target = Path(out_dir) / name
    with tempfile.TemporaryDirectory() as tmp:
        if source.adapter == "html":
            for page, _, text in html.pages(source, fetcher):
                (Path(tmp) / f"page-{page}.html").write_text(text, encoding="utf-8")
        else:
            for page, body in shopify.pages(source, fetcher):
                (Path(tmp) / f"products-page-{page}.json").write_text(
                    json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        target.mkdir(parents=True, exist_ok=True)
        for old in [*target.glob("products-page-*.json"), *target.glob("page-*.html")]:
            old.unlink()
        for new in sorted(Path(tmp).iterdir()):
            shutil.copy(new, target / new.name)
            print(f"wrote {target / new.name}")
