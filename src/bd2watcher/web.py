import json
import os
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bd2watcher.config import Config
from bd2watcher.health import BROKEN_AFTER
from bd2watcher.notifiers import STOCK_WORDS, price_text, usd
from bd2watcher.store import Store

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
STOCK_ORDER = {"in_stock": 0, "preorder": 1, "unknown": 2, "sold_out": 3}


def local_time(moment: datetime) -> str:
    """Format a time in the configured zone (TZ), labelled, e.g. 2026-10-17 05:00 MST."""
    zone = ZoneInfo(os.environ.get("TZ") or "UTC")
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M %Z")


templates.env.filters["local_time"] = local_time
STATIC = Path(__file__).parent / "static"
CHART_JS = "/static/chart-4.4.1.umd.js"  # vendored from npm (MIT), so the dashboard works offline


def create_app(config: Config, store: Store) -> FastAPI:
    """The read-only dashboard, reading through one long-lived connection."""
    app = FastAPI(title="BD2 Watcher", docs_url=None, redoc_url=None, openapi_url=None)
    labels = {s.name: s.display_name for s in config.sources}

    lock = threading.Lock()  # requests run on worker threads but share the connection
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        with lock:
            enabled = config.enabled_sources
            listings = [l for l in store.listings() if l.source in {s.name for s in enabled}]
            checks = {s.name: store.last_check(s.name) for s in enabled}
            streaks = {s.name: store.failure_streak(s.name)[0] for s in enabled}
            sets = [a for a in store.sets() if a.source in {s.name for s in enabled}]
            rates = {c: store.usd_rate(c) for c in {l.currency for l in listings}}

        products = defaultdict(list)
        for l in listings:
            products[(l.series, l.kind, l.product or l.title)].append(l)
        rows = [
            {
                "series": series, "kind": kind, "product": product,
                "href": "/product?" + urlencode({"name": product, "series": series, "kind": kind}),
                "offers": [
                    {"listing": o, "price": price_text(o.price, o.currency, rates.get(o.currency))}
                    # In stock first; within that, cheapest in USD; prices we can't convert yet come last.
                    for o in sorted(offers, key=lambda o: (
                        STOCK_ORDER[o.stock_state], o.price is None or rates.get(o.currency) is None,
                        usd(o.price, rates[o.currency]) if o.price is not None and rates.get(o.currency) else 0,
                    ))
                ],
            }
            for (series, kind, product), offers in sorted(
                products.items(), key=lambda kv: (kv[0][0], kv[0][1] != "sealed", kv[0][2])
            )
        ]
        return templates.TemplateResponse(request, "overview.html", {
            "rows": rows, "labels": labels, "stock_words": STOCK_WORDS, "sets": sets,
            "series_on_sale": {l.series for l in listings},
            "official_minutes": config.intervals.official_minutes,
            "sources": [(s.name, labels[s.name], checks[s.name], streaks[s.name]) for s in enabled],
            "broken_after": BROKEN_AFTER,
        })

    @app.get("/product", response_class=HTMLResponse)
    def product(request: Request, name: str, series: str | None = None, kind: str | None = None):
        with lock:
            enabled = {s.name for s in config.enabled_sources}
            listings = [l for l in store.listings() if l.source in enabled and (l.product or l.title) == name
                        and series in (None, l.series) and kind in (None, l.kind)]
            if not listings:
                raise HTTPException(404, "No such product")
            histories = {(l.source, l.external_id): store.price_history(l.source, l.external_id) for l in listings}
            last_ok = {l.source: store.last_successful_check(l.source) for l in listings}
            currencies = {p.currency for h in histories.values() for p in h} | {l.currency for l in listings}
            rates = {c: store.usd_rate(c) for c in currencies}

        several_per_store = len({l.source for l in listings}) < len(listings)
        datasets, missing_rates = [], set()
        for l in listings:
            history = histories[(l.source, l.external_id)]
            points = []
            for p in history:
                if rates.get(p.currency) is None:
                    missing_rates.add(p.currency)
                else:
                    points.append({"x": p.at.isoformat(), "y": float(usd(p.price, rates[p.currency]))})
            if not points:
                continue
            # The latest price still holds, so carry the line on to the store's last successful check.
            if last_ok[l.source] and last_ok[l.source] > history[-1].at:
                points.append({"x": last_ok[l.source].isoformat(), "y": points[-1]["y"]})
            label = labels.get(l.source, l.source)
            datasets.append({"label": f"{label} ({l.title})" if several_per_store else label, "data": points})
        return templates.TemplateResponse(request, "product.html", {
            "name": name, "chart_js": CHART_JS, "missing_rates": sorted(missing_rates),
            "chart_data": json.dumps({"datasets": datasets}).replace("</", "<\\/"),
            "offers": [{"listing": l, "price": price_text(l.price, l.currency, rates.get(l.currency))} for l in listings],
            "labels": labels, "stock_words": STOCK_WORDS,
            "history": sorted(
                ({"at": p.at, "store": labels.get(l.source, l.source),
                  "price": price_text(p.price, p.currency, rates.get(p.currency))}
                 for l in listings for p in histories[(l.source, l.external_id)]),
                key=lambda r: r["at"], reverse=True,
            ),
        })

    return app
