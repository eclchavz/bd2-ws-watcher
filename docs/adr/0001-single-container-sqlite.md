# 0001: One Docker container with SQLite, private dashboard

**Status:** accepted

The scheduler, the adapters, the alerting and the dashboard run in one Python process in one Docker container. State lives in a SQLite file on a mounted volume.

The dashboard has no login. It is reachable only on the home network when it runs on the PC, and only through Tailscale when it runs in the cloud. It is never exposed to the public internet.

## Why

- One user, a few hundred listings and checks every 10 minutes don't need a separate database or worker.
- The same image runs on the PC now and on a Google Cloud e2-micro (1 GB RAM, free tier) later, with Hetzner as the fallback. To fit in 1 GB, adapters must not need a headless browser by default.
- Avoiding a public dashboard means we never have to build authentication.

## Consequences

- Moving to the public internet would require adding authentication first. This decision would need to be reopened.
- The GitHub Actions or Pages approach was rejected because its scheduled runs are delayed, often by 15 minutes or more, and restocks sell out faster than that.
