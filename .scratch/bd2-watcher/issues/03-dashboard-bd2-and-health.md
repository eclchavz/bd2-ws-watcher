# 03: Dashboard with the Brown Dust 2 table and source status

**What to build:** A read-only page served by the same container on a port on the home network. It opens with a Brown Dust 2 section: one row per product, showing each store's price, stock state and buy link. A sources section shows each source's last check time and whether it's OK.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] A Seam 2 test: a database seeded through a check cycle renders a page that lists each Brown Dust 2 product with every store's price, stock state and link
- [ ] Listings for the same product from different stores group under one product row
- [ ] A Seam 2 test: the sources section shows the last check time and OK or broken for each source
- [ ] Server-rendered templates with no front-end build step
- [ ] It opens from a phone on the same Wi-Fi at `http://<pc-ip>:<port>`, with that port set in compose
- [ ] No login. The README warns never to expose the port to the internet (ADR 0001).
