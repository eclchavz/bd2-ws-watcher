# 06: Official JP site

**What to build:** An `official-jp` adapter that reads ws-tcg.com's product or news listings (use RSS if there is one) every 60 minutes. Each announced set becomes a stored set with title, release date, product types and link. A new Brown Dust 2 set or product sends an immediate Discord alert. Other new sets are stored as `new_set` events and queued for the digest (sending the digest is ticket 08). The sets also appear on the dashboard's upcoming-sets section.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] The page structure (or RSS feed) is confirmed live with `check-now official-jp`, and a fixture is captured
- [ ] A Seam 1 test: a fixture with a new Brown Dust 2 product sends one immediate alert
- [ ] A Seam 1 test: a fixture with a new set from another series creates a queued `new_set` event and no immediate alert
- [ ] The first check of the site is a silent baseline
- [ ] Japanese dates are parsed into release dates
- [ ] A Seam 2 test: the dashboard lists upcoming and recent sets with release dates, plus store links when a matching listing exists
