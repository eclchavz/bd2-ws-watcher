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

## Develop

```sh
uv sync
uv run pytest
uv run bd2watcher check-now
```

Tests never touch the network. They replay saved responses from `tests/fixtures/`.
