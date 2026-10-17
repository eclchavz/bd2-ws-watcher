from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

TIMEOUT_SECONDS = 20


class RobotsDisallowed(Exception):
    pass


class HttpFetcher:
    """Polite HTTP client: identifies itself, honours robots.txt, and times out."""

    def __init__(self, user_agent: str, transport: httpx.BaseTransport | None = None):
        self.user_agent = user_agent
        self.client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            transport=transport,
        )
        self.robots: dict[str, RobotFileParser] = {}

    def get_json(self, url: str):
        self._check_robots(url)
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser()
            response = self.client.get(f"{origin}/robots.txt")
            # No robots.txt (4xx) means everything is allowed.
            parser.parse([] if response.status_code >= 400 else response.text.splitlines())
            self.robots[origin] = parser
        if not self.robots[origin].can_fetch(self.user_agent, url):
            raise RobotsDisallowed(url)
