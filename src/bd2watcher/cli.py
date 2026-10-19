import argparse
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import threading

import uvicorn
from apscheduler.schedulers.blocking import BlockingScheduler

from bd2watcher.config import Config, load_config
from bd2watcher.cycle import find_watched, run_check
from bd2watcher.discover import capture_fixture, discover
from bd2watcher.fetcher import HttpFetcher
from bd2watcher.models import Alert, Listing
from bd2watcher.digest import run_digest
from bd2watcher.notifiers import DiscordNotifier, DryRunNotifier, EmailNotifier, NtfyNotifier
from bd2watcher.official import fetch as fetch_official, run_official_check
from bd2watcher.store import Store
from bd2watcher.web import create_app

log = logging.getLogger("bd2watcher")


def check_now(config: Config, fetcher, source_names: list[str]) -> None:
    """Check sources live and print what was found. Saves nothing and sends nothing."""
    for name in source_names or [s.name for s in config.enabled_sources]:
        if config.source(name).is_official:
            announcements = fetch_official(config.source(name), config, fetcher)
            print(f"{name}: {len(announcements)} products listed")
            for a in announcements:
                print(f"  [{a.series or '-'}] {a.title} | {a.release_date or 'no date'} | {a.url}")
            continue
        listings = find_watched(config.source(name), config, fetcher)
        print(f"{name}: {len(listings)} watched listings")
        for l in listings:
            print(f"  [{l.kind}] {l.title} | {l.price} {l.currency} | {l.stock_state} | {l.url}")


def build_notifiers(config: Config, dry_run: bool) -> list:
    """One notifier per channel, from secrets in the environment. Dry run swaps each for a logger.

    Discord is required. Email (instant alerts plus the daily digest) and ntfy are optional.
    """
    env = {k: os.environ.get(k, "").strip() for k in
           ("DISCORD_WEBHOOK_URL", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "NTFY_URL")}
    channels = ["discord"]
    if env["GMAIL_ADDRESS"] and env["GMAIL_APP_PASSWORD"]:
        channels.append("email")
    else:
        log.warning("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set: no email alerts and no daily digest")
    if env["NTFY_URL"]:
        channels.append("ntfy")
    if dry_run or config.alerts.dry_run:
        return [DryRunNotifier(c) for c in channels]
    if not env["DISCORD_WEBHOOK_URL"]:
        raise SystemExit("DISCORD_WEBHOOK_URL is not set in .env. Set it, or use --dry-run.")
    made = {
        "discord": lambda: DiscordNotifier(env["DISCORD_WEBHOOK_URL"]),
        "email": lambda: EmailNotifier(env["GMAIL_ADDRESS"], env["GMAIL_APP_PASSWORD"]),
        "ntfy": lambda: NtfyNotifier(env["NTFY_URL"]),
    }
    return [made[c]() for c in channels]


def send_test_alert(notifiers: list, channel: str) -> None:
    sample = Listing(
        source="test", external_id="0", title="Test alert from bd2-ws-watcher (Brown Dust 2 Booster Box)",
        url="https://github.com/eclchavz/bd2-ws-watcher", series="Brown Dust 2", kind="sealed",
        price=Decimal("54.99"), currency="USD", stock_state="in_stock",
    )
    for notifier in notifiers:
        if notifier.channel == channel:
            notifier.send(Alert("restock", notifier.label, sample, "Test store", datetime.now(timezone.utc)))
            print(f"Sent a test alert via {notifier.label}")
            return
    raise SystemExit(f"No notifier for channel {channel!r}")


def run(config: Config, db_path: str, notifiers: list, port: int) -> None:
    """Check every source now and then on its interval, and serve the dashboard, until stopped.

    The dashboard runs on its own thread, so a dashboard failure (say, port in use) never stops the checks.
    """
    fetcher = HttpFetcher(config.user_agent)
    scheduler = BlockingScheduler()
    minutes = config.intervals.store_minutes
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    def check(name: str) -> None:
        store = Store(db_path)
        source = config.source(name)
        try:
            if source.is_official:
                run_official_check(source, config, fetcher, store, datetime.now(timezone.utc), notifiers)
            else:
                listings = run_check(source, config, fetcher, store, datetime.now(timezone.utc), notifiers)
                log.info("%s: %d watched listings", name, len(listings))
        finally:
            store.close()

    for source in config.enabled_sources:
        every = config.intervals.official_minutes if source.is_official else minutes
        scheduler.add_job(
            # jitter is in seconds: minutes * 6 is 10% of the interval.
            check, "interval", args=[source.name], minutes=every, jitter=every * 6,
            next_run_time=datetime.now(timezone.utc), id=source.name, max_instances=1,
        )
    app = create_app(config, Store(db_path))
    threading.Thread(
        target=uvicorn.run, args=(app,), kwargs={"host": "0.0.0.0", "port": port, "log_level": "warning"},
        name="dashboard", daemon=True,
    ).start()
    log.info("Dashboard on port %d", port)

    def digest() -> None:
        store = Store(db_path)
        try:
            run_digest(config, store, notifiers, datetime.now(timezone.utc))
        finally:
            store.close()

    hour, minute = (int(x) for x in config.alerts.digest_time.split(":"))
    scheduler.add_job(digest, "cron", hour=hour, minute=minute, timezone=os.environ.get("TZ") or "UTC", id="digest")
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser(prog="bd2watcher")
    parser.add_argument("--config", default=os.environ.get("BD2_CONFIG", "config/config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    dry_run = argparse.ArgumentParser(add_help=False)
    dry_run.add_argument("--dry-run", action="store_true", help="log alerts instead of sending them")
    commands.add_parser("run", parents=[dry_run], help="check on a schedule until stopped")
    discover_parser = commands.add_parser("discover", help="report each store's platform, currency and collections")
    discover_parser.add_argument("sources", nargs="*", help="source names (default: all, including disabled)")
    capture_parser = commands.add_parser("capture-fixture", help="save a store's current pages for tests")
    capture_parser.add_argument("source")
    capture_parser.add_argument("--out", default="tests/fixtures")
    test_parser = commands.add_parser("send-test-alert", parents=[dry_run], help="send a sample alert to one channel")
    test_parser.add_argument("channel", choices=["discord", "email", "ntfy"])
    check_parser = commands.add_parser("check-now", help="check live and print, without saving")
    check_parser.add_argument("sources", nargs="*", help="source names (default: all enabled sources)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    if args.command == "check-now":
        check_now(config, HttpFetcher(config.user_agent), args.sources)
    elif args.command == "discover":
        discover(config, HttpFetcher(config.user_agent), args.sources)
    elif args.command == "capture-fixture":
        capture_fixture(config, HttpFetcher(config.user_agent), args.source, args.out)
    elif args.command == "send-test-alert":
        send_test_alert(build_notifiers(config, args.dry_run), args.channel)
    else:
        run(config, os.environ.get("BD2_DB", "data/bd2watcher.db"), build_notifiers(config, args.dry_run),
            int(os.environ.get("BD2_PORT", "8080")))


if __name__ == "__main__":
    main()
