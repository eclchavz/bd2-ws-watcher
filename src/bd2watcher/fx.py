import logging
from datetime import datetime

from bd2watcher.store import Store

log = logging.getLogger(__name__)

DEFAULT_URL = "https://api.frankfurter.dev/v1/latest?base={currency}&symbols=USD"


def refresh_rates(store: Store, fetcher, currencies: set[str], now: datetime, url: str = DEFAULT_URL) -> None:
    """Fetch each currency's USD rate at most once a (UTC) day. If the API is down, the last stored rate stays."""
    for currency in sorted(c for c in currencies if c and c != "USD"):
        fetched = store.rate_fetched_at(currency)
        if fetched is not None and fetched.date() == now.date():
            continue
        try:
            rate = fetcher.get_json(url.format(currency=currency))["rates"]["USD"]
            store.save_rate(currency, rate, now)
        except Exception as e:
            log.warning("Couldn't refresh the %s to USD rate (%s: %s); keeping the last one", currency,
                        type(e).__name__, e)
