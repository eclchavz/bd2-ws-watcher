import os
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bd2watcher.config import Config
from bd2watcher.notifiers import STOCK_WORDS
from bd2watcher.store import Store

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
STOCK_ORDER = {"in_stock": 0, "preorder": 1, "unknown": 2, "sold_out": 3}


def local_time(moment: datetime) -> str:
    """Format a time in the configured zone (TZ), labelled, e.g. 2026-10-17 05:00 MST."""
    zone = ZoneInfo(os.environ.get("TZ") or "UTC")
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")


templates.env.filters["local_time"] = local_time


def create_app(config: Config, store: Store) -> FastAPI:
    """The read-only dashboard, reading through one long-lived connection."""
    app = FastAPI(title="BD2 Watcher", docs_url=None, redoc_url=None, openapi_url=None)
    labels = {s.name: s.display_name for s in config.sources}
    enabled = [s for s in config.sources if s.enabled]
    lock = threading.Lock()  # requests run on worker threads but share the connection

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        with lock:
            listings = store.listings()
            checks = {s.name: store.last_check(s.name) for s in enabled}

        products = defaultdict(list)
        for l in listings:
            products[(l.series, l.kind, l.product or l.title)].append(l)
        rows = [
            {
                "series": series, "kind": kind, "product": product,
                "offers": sorted(offers, key=lambda o: (STOCK_ORDER[o.stock_state], o.price is None, o.price or 0)),
            }
            for (series, kind, product), offers in sorted(
                products.items(), key=lambda kv: (kv[0][0], kv[0][1] != "sealed", kv[0][2])
            )
        ]
        return templates.TemplateResponse(request, "overview.html", {
            "rows": rows, "labels": labels, "stock_words": STOCK_WORDS,
            "sources": [(s.name, labels[s.name], checks[s.name]) for s in enabled],
        })

    return app
