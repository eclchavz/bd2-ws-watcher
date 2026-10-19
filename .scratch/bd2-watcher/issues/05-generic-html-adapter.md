# 05: Checker for non-Shopify stores

**What to build:** An `html` adapter driven only by CSS selectors in config (product card, title, price, currency, stock text, link, next page). Any non-Shopify store found in ticket 04 is then watched the same way as a Shopify store. Skip and close this ticket if every store is Shopify.

**Blocked by:** 04

**Status:** done (on branch `ticket/05-html-adapter`). Built ahead of need with hand-made fixtures. Whether any store actually needs it is decided by the `discover` run in ticket 04.

- [x] A Seam 1 test: a captured HTML fixture for each non-Shopify store produces the expected watched listings, with price, currency and stock state
- [x] Stock text maps to `in_stock`, `preorder` or `sold_out` using per-source patterns in config, and to `unknown` when nothing matches
- [x] Adding a similar store needs config only
- [x] No headless browser. If a store truly needs one, record that here and make Playwright an opt-in extra for that source only (ADR 0001).
