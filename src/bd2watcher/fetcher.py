import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

TIMEOUT_SECONDS = 20
ROBOTS_MAX_AGE_SECONDS = 24 * 3600
MAX_REDIRECTS = 5


class RobotsDisallowed(Exception):
    pass


class HttpFetcher:
    """Polite HTTP client: identifies itself, honours robots.txt (including on redirects), and times out."""

    def __init__(self, user_agent: str, transport: httpx.BaseTransport | None = None):
        self.user_agent = user_agent
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
        )
        self.clock = time.monotonic
        self.robots: dict[str, tuple[float, RobotFileParser]] = {}

    def get_json(self, url: str):
        for _ in range(MAX_REDIRECTS + 1):
            self._check_robots(url)
            response = self.client.get(url)
            if not response.is_redirect:
                response.raise_for_status()
                return response.json()
            url = urljoin(url, response.headers["location"])
        raise httpx.TooManyRedirects(f"More than {MAX_REDIRECTS} redirects", request=response.request)

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self.robots.get(origin)
        if cached is None or self.clock() - cached[0] > ROBOTS_MAX_AGE_SECONDS:
            cached = (self.clock(), self._read_robots(origin))
            self.robots[origin] = cached
        if not cached[1].can_fetch(self.user_agent, url):
            raise RobotsDisallowed(url)

    def _read_robots(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        response = self.client.get(f"{origin}/robots.txt")
        if response.status_code >= 500:
            parser.disallow_all = True  # RFC 9309: unreachable robots.txt means disallow everything
        elif response.status_code >= 400:
            parser.parse([])  # no robots.txt means everything is allowed
        else:
            parser.parse(response.text.splitlines())
        return parser
