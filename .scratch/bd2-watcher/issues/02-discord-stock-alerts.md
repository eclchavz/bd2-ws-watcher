# 02: Restock and new-listing alerts to Discord

**What to build:** When a check finds a change in a watched listing, a Discord message goes out with the product name, store, native price, stock state and link. The changes are a `new_listing`, a `restock` (`sold_out` to `in_stock`) or a `preorder_opened`. The first successful check of a source is a silent baseline. Each listing gets at most one stock alert per 6 hours. A dry-run mode logs alerts instead of sending them. `send-test-alert discord` sends a sample message.

**Blocked by:** 01

**Status:** done (on branch `ticket/02-discord-alerts`). A real Discord send still needs a run from the user's PC, since the build environment blocks discord.com.

- [x] A Seam 1 test: the first check of a source records a baseline and sends no alerts
- [x] A Seam 1 test: a listing going from `sold_out` to `in_stock` sends exactly one `restock` alert
- [x] A Seam 1 test: a new watched listing sends one `new_listing` alert, and a listing turning to preorder sends `preorder_opened`
- [x] A Seam 1 test: a listing that flips between in stock and sold out 4 times in 6 hours sends only one alert. A flip after the 6 hours pass sends another.
- [x] A Seam 1 test: a listing that stays in stock sends nothing on later checks
- [x] On startup, a check runs right away and alerts on changes since the last stored state
- [x] Every event and every alert sent is recorded in the database
- [x] Dry-run mode (config or flag) records alerts as sent to `dry-run` and makes no network calls
- [x] Alerts go to Discord at any hour (no quiet hours)
- [x] The Discord webhook URL comes only from `.env`
- [x] A listing missing from a successful check (delisted, or no longer matching) is marked `sold_out`, not left at its old stock state. It alerts again if it reappears. (From the ticket 01 code review.)
