from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bd2watcher.config import Config
from bd2watcher.notifiers import STOCK_WORDS
from bd2watcher.store import Store

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
STOCK_ORDER = {"in_stock": 0, "preorder": 1, "unknown": 2, "sold_out": 3}


def create_app(config: Config, store_factory) -> FastAPI:
    """The read-only dashboard. `store_factory` is a Store, or a callable returning a fresh one per request."""
    app = FastAPI(title="BD2 Watcher", docs_url=None, redoc_url=None, openapi_url=None)
    labels = {s.name: s.display_name for s in config.sources}

    def open_store() -> tuple[Store, bool]:
        if isinstance(store_factory, Store):
            return store_factory, False
        return store_factory(), True

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        store, owned = open_store()
        try:
            listings = store.listings()
            checks = {s.name: store.last_check(s.name) for s in config.sources}
        finally:
            if owned:
                store.close()

        products = defaultdict(list)
        for l in listings:
            products[(l.series, l.kind, l.product or l.title)].append(l)
        rows = [
            {
                "series": series, "kind": kind, "product": product,
                "offers": sorted(offers, key=lambda o: (STOCK_ORDER[o.stock_state], o.price or 0)),
            }
            for (series, kind, product), offers in sorted(products.items(), key=lambda kv: (kv[0][0], kv[0][1] != "sealed", kv[0][2]))
        ]
        return templates.TemplateResponse(request, "overview.html", {
            "rows": rows, "labels": labels, "stock_words": STOCK_WORDS,
            "sources": [(s.name, labels[s.name], checks[s.name]) for s in config.sources],
        })

    return app
