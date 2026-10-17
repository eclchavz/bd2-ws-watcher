# Glossary

**Source**: a website we check. It is either an **official site** (Weiss Schwarz JP or EN) or a **store**.

**Adapter**: the code that reads one kind of source and returns what it found. Kinds: `shopify` (reads the store's `products.json`), `html` (reads product pages using CSS selectors from config), `official-jp`, `official-en`.

**Product**: a thing you can buy, such as "Brown Dust 2 Booster Box (JP)". It is the same product no matter which store sells it.

**Listing**: one product at one store, with its current price, currency, stock state and URL. Price history belongs to a listing.

**Stock state**: one of `in_stock`, `preorder`, `sold_out`, `unknown`.

**Kind**: how a product is classified. `sealed` (booster pack, box, case, trial deck), `supply` (official sleeves, playmats, deck boxes) or `other` (ignored, including single cards).

**Watchlist**: the configured keyword sets that mark a product as part of a tracked series. The only watched series to begin with is Brown Dust 2 (`Brown Dust 2`, `BrownDust2`, `ブラウンダスト2`, plus its set code).

**Set**: a Weiss Schwarz release announced on an official site, with a title, language, release date and product types.

**Check**: one run of one adapter against one source.

**Snapshot**: what a check returned. It is compared against stored state.

**Baseline**: the first successful check of a source. It is recorded silently and creates no events, so adding a source never floods you with alerts.

**Event**: a detected change: `new_listing`, `restock`, `preorder_opened`, `price_changed`, `new_set`, `english_release`, `source_broken`, `source_recovered`.

**Alert**: an event delivered through a **channel** (`discord`, `ntfy`, `email`). An event can produce zero or more alerts.

**Cooldown**: the 6-hour window during which a second stock alert for the same listing is suppressed.

**Digest**: the daily 9:00 AM email summarising new Weiss Schwarz sets.

**Source health**: the status of each source (last check, OK, or broken after 3 failed checks in a row).
