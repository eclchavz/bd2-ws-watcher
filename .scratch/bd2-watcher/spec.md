# Spec: BD2 / Weiss Schwarz watcher

**Status:** ready-for-agent

## Problem Statement

I collect Weiss Schwarz sealed product, and above all Brown Dust 2. The Brown Dust 2 Japanese Trial Deck and Booster came out on July 3, 2026, and the booster already sells out at some stores. Restocks and preorders open without warning across several stores, and they're often gone within minutes. Bushiroad announces new Weiss Schwarz sets on two separate official sites (Japanese and English). Checking six stores and two official sites by hand is tedious, and I miss restocks. I have no single place that shows which sets are coming, where to buy or preorder them, and what they cost over time.

## Solution

A small app that runs in one Docker container on my PC, and can later move unchanged to a free cloud server. Every 10 minutes it checks my stores for Brown Dust 2 sealed product and official supplies. Every hour it checks the official JP and EN Weiss Schwarz sites for announcements. When something I care about changes, such as a new Brown Dust 2 product, a restock, a preorder opening, or an English release, I get a Discord message and an email right away. New Weiss Schwarz sets of other series reach me as one email summary each morning. A dashboard on my home network shows all Brown Dust 2 listings with live prices, stock and buy links, upcoming Weiss Schwarz sets, price history charts, past alerts, and whether each source check is working.

## User Stories

1. As a collector, I want an alert when a Brown Dust 2 sealed product appears at any store I watch, so that I can buy it before it sells out.
2. As a collector, I want an alert when a sold-out Brown Dust 2 listing comes back in stock, so that I can catch restocks.
3. As a collector, I want an alert when a Brown Dust 2 preorder opens at a store, so that I can reserve a copy early.
4. As a collector, I want an alert when the official JP or EN site announces a new Brown Dust 2 product, so that I know about it before stores list it.
5. As a collector, I want a specific alert when an English Brown Dust 2 release is announced, so that I can decide between the JP and EN versions.
6. As a collector, I want official Brown Dust 2 supplies (sleeves, playmats, deck boxes) to alert the same way as sealed product, so that I don't miss limited supplies.
7. As a collector, I want single cards ignored completely, so that my alerts stay about sealed product.
8. As a collector, I want one email each morning at 9:00 AM local time listing newly announced Weiss Schwarz sets from any series, so that I stay informed without a stream of pings.
9. As a collector, I want Brown Dust 2 alerts sent to Discord and email at any hour, so that I can act on a restock in the middle of the night.
10. As a collector, I want each alert to include the product name, store, price (native currency and approximate USD), stock state and a direct link, so that I can buy in one tap.
11. As a collector, I want at most one stock alert per listing per 6 hours, so that a store flipping its stock flag doesn't spam me.
12. As a collector, I want the first check of a new source to be recorded silently, so that adding a store doesn't flood me with "new" alerts.
13. As a collector, I want the app to check right away when it starts and alert on what changed while it was down, so that downtime doesn't cost me a restock.
14. As a collector, I want a Discord notice when a source has failed 3 checks in a row, and another when it recovers, so that a broken check can't silently miss a restock.
15. As a collector, I want to open the dashboard from my PC or phone on my home Wi-Fi, so that I can see the current state at a glance.
16. As a collector, I want the dashboard to show a Brown Dust 2 section first, with every product and each store's price, stock state and buy link, so that I can compare stores.
17. As a collector, I want the dashboard to list upcoming and recently released Weiss Schwarz sets (JP and EN) with release dates and known preorder links, so that I can plan purchases.
18. As a collector, I want a price history chart per product with one line per store, in approximate USD, so that I can tell a good price from a markup.
19. As a collector, I want price drops shown on the dashboard but not alerted, so that alerts stay about availability.
20. As a collector, I want the dashboard to show a log of past alerts, so that I can see what I missed.
21. As a collector, I want the dashboard to show each source's last check time and health, so that I can trust what I'm seeing.
22. As the maintainer, I want to add a store by editing config only when it's a Shopify store or fits the generic HTML adapter, so that I don't have to write code for each new store.
23. As the maintainer, I want the watchlist keywords in config, including Japanese names and set codes, so that I can add another series later without code changes.
24. As the maintainer, I want secrets (Discord webhook, Gmail app password, ntfy topic) in a `.env` file kept out of git, so that I can publish the repo safely.
25. As the maintainer, I want a `check-now` command that checks every source live and prints what it found without sending alerts, so that I can confirm an adapter works.
26. As the maintainer, I want a dry-run mode that logs alerts instead of sending them, so that I can test changes safely.
27. As the maintainer, I want a `capture-fixture` command that saves a source's current response, so that a site redesign becomes a quick fixture update and a failing test.
28. As the maintainer, I want ntfy as an optional extra channel that I switch on in config, so that I can add phone push later.
29. As the maintainer, I want to run the same container on a free Google Cloud e2-micro server reached through Tailscale, so that checks keep running when my PC is off.
30. As the maintainer, I want the app to fit in 1 GB of RAM, so that it can run on the free tier.
31. As the maintainer, I want check intervals, cooldown, digest time and time zone in config, so that I can tune them without touching code.
32. As a polite visitor, I want the app to identify itself, respect robots.txt and back off after errors, so that stores don't block it.

## Implementation Decisions

- **Stack:** Python 3.12, httpx, selectolax (or BeautifulSoup) for HTML, pydantic for config and models, APScheduler running inside the same process, FastAPI with Jinja templates for the dashboard, Chart.js loaded from a CDN for charts, SQLite on a Docker volume, and docker compose to run it. No headless browser by default. Playwright stays an opt-in extra for any one source that turns out to need it (see ADR 0001).
- **Config:** a YAML file listing sources (name, adapter kind, base URL, collection or search path, HTML selectors), watchlists (series name, keywords, set codes), product-kind keyword rules, intervals, cooldown, digest time, time zone (`TZ`) and which channels are on. Secrets come from `.env`.
- **Sources to begin with:** official JP (ws-tcg.com), official EN (en.ws-tcg.com), TCG Corner, Japan-Figure, Flipside Gaming, Jump Ichiban, Lumius (lumiusinc.com), Hammer Girl Anime (hammergirlanime.com). The first four look like Shopify stores. Lumius and Hammer Girl haven't been checked yet, and the first ticket confirms all of them.
- **Adapter interface:** each adapter takes a source config and an HTTP fetcher, and returns a snapshot of raw listings (title, URL, price, currency, availability flags, tags) or raw sets (title, language, release date, product types, link). Adapters don't touch the database, classify products or send anything.
  - `shopify`: reads `/products.json` (or a collection's `products.json`), paging through results. Stock is `in_stock` if any variant is available, `preorder` when the title or tags mention preorder (`pre-order`, `preorder`, `予約`), and `sold_out` otherwise.
  - `html`: CSS selectors from config, for any non-Shopify store.
  - `official-jp` / `official-en`: read each site's product or news list. Their page structure (and whether there's an RSS feed) is confirmed in a ticket, because it couldn't be reached from the planning environment.
- **Classifier:** a pure function from a raw listing or set to (watched series or none, kind `sealed`, `supply` or `other`, normalised product key). Matching ignores case and full-width/half-width differences. `other` is dropped. Listings that are both `sealed` and from a watched series go to the change detector. Sets go to the change detector whatever their series.
- **Change detector:** compares a snapshot with stored state and produces events (see `GLOSSARY.md`). The first successful check of a source is a baseline. Price changes are written as price points (only when the price changes) and produce `price_changed` events that never alert.
- **Alert router:** maps events to channels:
  - watched-series `new_listing`, `restock`, `preorder_opened`, `new_set` and `english_release`: Discord and email, sent immediately
  - unwatched `new_set`: added to the digest queue
  - `source_broken` and `source_recovered`: Discord only
  - `price_changed`: never alerts

  It applies the 6-hour per-listing cooldown to stock events and records every alert sent.
- **Notifiers:** Discord webhook, Gmail SMTP using an app password (from and to the user's own address), and optional ntfy. Each one is a small class behind a single `send(alert)` interface. A dry-run notifier logs alerts instead of sending.
- **Source health:** a check that raises, times out, or returns zero products where there used to be some counts as a failure. After 3 failures in a row the source is marked broken and `source_broken` fires once. The next success fires `source_recovered`.
- **FX:** one daily USD conversion rate per currency from a free no-key API (e.g. Frankfurter, which uses ECB rates). The native price and currency are always stored, and USD is computed when shown.
- **Scheduler:** on startup, run every check once. After that, stores run every 10 minutes and official sites every 60 minutes, each with ±10% jitter, and the digest goes out at 9:00 AM `TZ`. A per-host request limit and exponential backoff apply.
- **Storage (logical schema):** `sources`, `source_checks`, `products`, `listings`, `price_points`, `sets`, `events`, `alerts`, `fx_rates`. Plain SQL migrations, applied on startup.
- **Dashboard:** server-rendered pages. Overview (Brown Dust 2 section, then upcoming sets), product detail (price history chart), alerts log, and sources health. Read-only. Bound to the LAN port set in compose, with no auth (see ADR 0001).
- **CLI:** `run` (scheduler plus dashboard), `check-now [source]` (live, prints results, never alerts), `capture-fixture <source>`, `send-test-alert <channel>`.
- **Deployment:** docker compose on the PC first. Later, a guide plus compose override for a Google Cloud e2-micro (US region, free tier) reached through Tailscale, with Hetzner as the fallback.

## Testing Decisions

- Good tests check only external behaviour. Given these source responses and this stored state at this time, the tests assert which alerts were sent and what the dashboard shows. They never assert on internal function calls or SQL.
- **Seam 1, the check cycle:** run one check cycle with a fake HTTP fetcher serving fixtures, a fake clock, an in-memory SQLite database and a recording notifier. Almost every behaviour is tested here, including baseline, restock, preorder, cooldown, flapping, digest batching, source broken and recovered, singles ignored, Japanese keyword matching and price points.
- **Seam 2, the dashboard:** the FastAPI test client against a database seeded through Seam 1. It asserts that the rendered pages contain the expected listings, sets, alerts and health.
- Adapters are covered through Seam 1 with real captured fixtures (`tests/fixtures/<source>/...`), not with separate unit tests on parsing code.
- No live network calls in the test suite. `check-now` is the manual live smoke test.
- This is a new project, so there are no existing tests to follow. Use pytest.

## Out of Scope

- Single cards (no tracking, no alerts).
- eBay, TCGplayer and other marketplaces.
- SMS and Twilio.
- Price-drop alerts (price changes are shown on the dashboard only).
- A dashboard reachable from the public internet, user accounts, or login.
- Automatic carting or buying.
- More than one user.
- Watched series other than Brown Dust 2 at launch (the watchlist supports more through config).

## Further Notes

- **Facts still to verify (first tickets):** which platform Lumius and Hammer Girl Anime run on; the official JP and EN sites' page structure and whether they have RSS feeds; the Brown Dust 2 set code; whether each store's robots.txt allows `products.json`. None of these could be reached from the planning environment.
- **Sources used during planning:** [Bushiroad press release](https://www.gamedeveloper.com/press-release/trial-deck-booster-pack-browndust2-from-wei-schwarz-releases-friday-july-3-), [TCG Corner listing](https://tcg-corner.com/products/weiss-schwarz-brown-dust-2-booster-japanese-pre-order), [Japan-Figure listing](https://japan-figure.com/products/bushiroad-weiss-schwarz-brown-dust-2-tcg-booster-box-cards), [Google Cloud free tier](https://cloud.google.com/free/docs/compute-getting-started).
- The user's time zone isn't recorded yet. Set `TZ` in `.env` during setup.
- Decisions behind the design are in `docs/adr/0001-single-container-sqlite.md` and `docs/adr/0002-alert-on-transitions.md`.
