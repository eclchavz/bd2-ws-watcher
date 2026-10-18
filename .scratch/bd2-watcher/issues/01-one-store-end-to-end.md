# 01: One store, end to end

**What to build:** The project skeleton and the thinnest complete path through it. `docker compose up` starts one container that checks TCG Corner every 10 minutes (and once on startup) using the `shopify` adapter. It classifies each listing against the Brown Dust 2 watchlist and product-kind rules, drops `other`, and saves the watched `sealed` and `supply` listings to SQLite. `check-now tcg-corner` runs the same check live and prints the listings it found, without saving or alerting. Config comes from a YAML file plus `.env` (with `TZ=America/Phoenix` in `.env.example`).

**Blocked by:** None (can start immediately)

**Status:** done (on branch `ticket/01-one-store`). The fixture is hand-made until ticket 04, and `check-now` against the live site still needs a run from the user's PC.

- [x] `docker compose up` starts the container, and the SQLite file lives on a mounted volume that survives restarts
- [x] Config loads sources, the watchlist (`Brown Dust 2`, `BrownDust2`, `ブラウンダスト2`), kind rules and intervals from YAML. Secrets come from `.env`, and `.env.example` is committed.
- [x] A Seam 1 test: a check cycle using a captured TCG Corner `products.json` fixture, a fake fetcher, a fake clock and in-memory SQLite stores exactly the Brown Dust 2 sealed and supply listings, with the right price, currency and stock state
- [x] Single cards and unrelated products are not stored
- [x] Keyword matching ignores case and full-width/half-width differences (tested with a Japanese title)
- [x] `preorder` is detected from title or tags (`pre-order`, `preorder`, `予約`)
- [x] `check-now tcg-corner` prints the matched listings from the live site and writes nothing
- [x] The HTTP client sends an identifying User-Agent, respects robots.txt and has a timeout
