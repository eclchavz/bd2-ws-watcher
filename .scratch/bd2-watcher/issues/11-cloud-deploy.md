# 11: Cloud deploy

**What to build:** A guide plus a compose override for running the same image on a free Google Cloud e2-micro (US region), with the dashboard reachable only through Tailscale. Hetzner is documented as the fallback. Moving from the PC means copying the SQLite volume.

**Blocked by:** 02, 03, 08

**Status:** ready-for-human (needs the user's Google Cloud and Tailscale accounts)

- [ ] The container's memory stays under about 700 MB during a full check cycle (measured and noted)
- [ ] The guide covers creating the e2-micro within free-tier limits, installing Docker and Tailscale, copying `.env` and the database, and starting the app
- [ ] The dashboard port is bound to the Tailscale interface only, and a check from outside the tailnet confirms it's unreachable
- [ ] The container restarts automatically after a reboot
- [ ] The guide includes a short Hetzner section as the fallback
