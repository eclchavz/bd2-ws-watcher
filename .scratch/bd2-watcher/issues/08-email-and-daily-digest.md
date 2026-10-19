# 08: Email and the daily Weiss Schwarz summary

**What to build:** A Gmail SMTP channel using an app password, sending from and to the user's own address. Every watched-series alert now goes to both Discord and email. Every day at 9:00 AM in `TZ` (America/Phoenix), one summary email lists the queued `new_set` events and clears the queue. No email is sent on days with nothing new. `send-test-alert email` sends a sample.

**Blocked by:** 02, 06

**Status:** done (on branch `ticket/08-email-digest`). A real Gmail send still needs the user's app password.

- [x] A Seam 1 test: a Brown Dust 2 restock records alerts on both `discord` and `email`
- [x] A Seam 1 test: at 9:00 AM (fake clock), queued sets go out in one email, and a second run that day sends nothing
- [x] A Seam 1 test: with an empty queue, no email is sent
- [x] Gmail address and app password come only from `.env`, and the README walks through creating an app password
- [x] ntfy is available as an optional channel, switched on in config (`alerts.ntfy`, off by default) with NTFY_URL in .env
- [x] The routing table matches the spec (`source_broken` stays Discord-only, `price_changed` never alerts)
