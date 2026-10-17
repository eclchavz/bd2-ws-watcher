import argparse
import logging
import os
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from bd2watcher.config import Config, load_config
from bd2watcher.cycle import find_watched, run_check
from bd2watcher.fetcher import HttpFetcher
from bd2watcher.store import Store

log = logging.getLogger("bd2watcher")


def check_now(config: Config, fetcher, source_names: list[str]) -> None:
    """Check sources live and print what was found. Saves nothing and sends nothing."""
    for name in source_names or [s.name for s in config.sources]:
        listings = find_watched(config.source(name), config, fetcher)
        print(f"{name}: {len(listings)} watched listings")
        for l in listings:
            print(f"  [{l.kind}] {l.title} | {l.price} {l.currency} | {l.stock_state} | {l.url}")


def run(config: Config, db_path: str) -> None:
    """Check every source now, then on its interval, until stopped."""
    fetcher = HttpFetcher(config.user_agent)
    scheduler = BlockingScheduler()
    minutes = config.intervals.store_minutes
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    def check(name: str) -> None:
        store = Store(db_path)
        try:
            listings = run_check(config.source(name), config, fetcher, store, datetime.now(timezone.utc))
            log.info("%s: %d watched listings", name, len(listings))
        finally:
            store.close()

    for source in config.sources:
        scheduler.add_job(
            # jitter is in seconds: minutes * 6 is 10% of the interval.
            check, "interval", args=[source.name], minutes=minutes, jitter=minutes * 6,
            next_run_time=datetime.now(timezone.utc), id=source.name, max_instances=1,
        )
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser(prog="bd2watcher")
    parser.add_argument("--config", default=os.environ.get("BD2_CONFIG", "config/config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("run", help="check on a schedule until stopped")
    check_parser = commands.add_parser("check-now", help="check live and print, without saving")
    check_parser.add_argument("sources", nargs="*", help="source names (default: all)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    if args.command == "check-now":
        check_now(config, HttpFetcher(config.user_agent), args.sources)
    else:
        run(config, os.environ.get("BD2_DB", "data/bd2watcher.db"))


if __name__ == "__main__":
    main()
