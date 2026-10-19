# bd2-ws-watcher

Watches stores and the official Weiss Schwarz sites for Brown Dust 2 sealed product and new set announcements. It's one Docker container with a SQLite database.

The plan is in `.scratch/bd2-watcher/spec.md`, and the tickets are in `.scratch/bd2-watcher/issues/`.

## Run it on your PC

You need Docker Desktop.

```sh
cp .env.example .env        # then edit .env
docker compose up -d --build
docker compose logs -f      # watch the checks
```

The database lives in `./data/`, so it survives restarts and rebuilds. Sources, keywords and intervals are in `config/config.yaml`. After editing the config, run `docker compose restart`.

## Alerts

| What | Discord | Email | ntfy (optional) |
|---|---|---|---|
| Brown Dust 2 new product, restock, preorder, official announcement, English release | right away | right away | right away |
| Other new Weiss Schwarz sets | | daily summary at 9:00 AM (`digest_time`) | |

Test a channel with `docker compose run --rm bd2watcher bd2watcher send-test-alert discord` (or `email`, `ntfy`).

### Setting up Gmail

Gmail needs an **app password**, not your normal password:

1. Turn on 2-Step Verification for your Google account (Google Account, then Security).
2. Go to https://myaccount.google.com/apppasswords, create one named "bd2-watcher", and copy the 16-character password.
3. In `.env`, set `GMAIL_ADDRESS=you@gmail.com` and `GMAIL_APP_PASSWORD=<the 16 characters>`.
4. Run `docker compose restart`, then `send-test-alert email`.

Alerts are sent from and to that same address.

## Dashboard

Open http://localhost:8080 on the PC, or `http://<the PC's IP address>:8080` from your phone on the same Wi-Fi. To find the PC's IP on Windows, run `ipconfig` and look for "IPv4 Address".

The dashboard has no login. **Never forward port 8080 on your router or expose it to the internet.** For access away from home, run it in the cloud instead: see [docs/deploy-cloud.md](docs/deploy-cloud.md) (Google Cloud free tier plus Tailscale).

## Check a source by hand

Checks live and prints what it finds, without saving or alerting:

```sh
docker compose run --rm bd2watcher bd2watcher check-now tcg-corner
```

## Add or enable a store

Stores live in `config/config.yaml`. Only TCG Corner is enabled to begin with. The others stay disabled until checked from a machine that can reach them:

```sh
docker compose run --rm bd2watcher bd2watcher discover
```

For each store this prints whether it's Shopify, its currency, any Weiss Schwarz collections (with the `products_path` to use) and how many Brown Dust 2 listings it found. Then, for each store:

1. Set `currency` and `products_path` from the output, and remove `enabled: false`.
2. Check it: `bd2watcher check-now <name>`.
3. Save a test fixture: `bd2watcher capture-fixture <name>`. Commit `tests/fixtures/<name>/`.

A store that `discover` reports as not Shopify needs the `html` adapter (ticket 05).

## Develop

```sh
uv sync
uv run pytest
uv run bd2watcher check-now
```

Tests never touch the network. They replay saved responses from `tests/fixtures/`.
