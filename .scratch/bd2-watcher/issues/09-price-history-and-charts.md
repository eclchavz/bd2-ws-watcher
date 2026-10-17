# 09: Price history and USD charts

**What to build:** Store a price point whenever a listing's price changes. Fetch a daily USD conversion rate for each currency in use from a free no-key API (e.g. Frankfurter). A product detail page shows a line chart of approximate USD price over time, with one line per store. Native prices stay visible, and approximate USD shows next to prices on the dashboard and in alerts.

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] A Seam 1 test: an unchanged price adds no price point, and a changed price adds one and records `price_changed` with no alert
- [ ] Exchange rates are fetched at most once a day, stored, and the most recent stored rate is used when the API is down
- [ ] A Seam 2 test: the product page contains chart data with one series per store, in USD
- [ ] The chart library loads from a pinned CDN version, with no build step
- [ ] Alerts show the native price and approximate USD (e.g. `¥5,940 (~$39)`)
