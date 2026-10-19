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

## Dashboard

Open http://localhost:8080 on the PC, or `http://<the PC's IP address>:8080` from your phone on the same Wi-Fi. To find the PC's IP on Windows, run `ipconfig` and look for "IPv4 Address".

The dashboard has no login. **Never forward port 8080 on your router or expose it to the internet.** For access away from home, see ticket 11 (Tailscale).

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
