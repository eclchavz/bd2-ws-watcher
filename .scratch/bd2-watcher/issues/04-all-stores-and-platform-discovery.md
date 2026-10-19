# 04: Add all stores and identify their platforms

**What to build:** A `discover` command that the user runs from their PC (the planning environment couldn't reach these sites). For each configured store, it reports whether the store is Shopify (a `products.json` endpoint is present), what robots.txt says, and a suggested collection or search path. Every Shopify store gets added through config only. `capture-fixture <source>` saves each store's current response under `tests/fixtures/`. Stores: TCG Corner, Japan-Figure, Flipside Gaming, Jump Ichiban, Lumius (lumiusinc.com), Hammer Girl Anime (hammergirlanime.com).

**Blocked by:** 01

**Status:** code done (on branch `ticket/04-all-stores`). Waiting on a `discover` run from the user's PC: the build sandbox can't reach any store.

All six stores are in config. TCG Corner is enabled; the other five are disabled until discover confirms them.

- [x] `discover` prints platform, robots.txt status and a suggested path for every configured store
- [x] `capture-fixture <source>` writes a fixture that a Seam 1 test can replay
- [ ] Every Shopify store is configured and has a fixture-backed Seam 1 test showing its Brown Dust 2 listings are found
- [ ] The platform of Lumius and Hammer Girl is recorded in the spec's Further Notes
- [ ] Any non-Shopify store is listed in ticket 05, or ticket 05 is closed as not needed
- [ ] The Brown Dust 2 set code is added to the watchlist if it shows up in store listings
