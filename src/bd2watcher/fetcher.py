import re
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

TIMEOUT_SECONDS = 20
ROBOTS_MAX_AGE_SECONDS = 24 * 3600
MAX_REDIRECTS = 5


META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?([\w-]+)", re.IGNORECASE)


def decode_html(content: bytes, header_charset: str | None) -> str:
    """Decode a page using the HTTP charset, else a <meta charset> in its first 4 KB, else UTF-8."""
    charset = header_charset
    if not charset:
        match = META_CHARSET.search(content[:4096])
        charset = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


class RobotsDisallowed(Exception):
    pass


class RobotsUnavailable(RobotsDisallowed):
    """robots.txt answered with a server error, so we treat everything as disallowed for now."""


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
        return self._get(url).json()

    def get_text(self, url: str) -> str:
        response = self._get(url)
        return decode_html(response.content, response.charset_encoding)

    def _get(self, url: str) -> httpx.Response:
        for _ in range(MAX_REDIRECTS + 1):
            self._check_robots(url)
            response = self.client.get(url)
            if not response.is_redirect:
                response.raise_for_status()
                return response
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
            raise (RobotsUnavailable if getattr(cached[1], "unavailable", False) else RobotsDisallowed)(url)

    def _read_robots(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        response = self.client.get(f"{origin}/robots.txt")
        if response.status_code >= 500:
            parser.disallow_all = True  # RFC 9309: unreachable robots.txt means disallow everything
            parser.unavailable = True
        elif response.status_code >= 400:
            parser.parse([])  # no robots.txt means everything is allowed
        else:
            parser.parse(response.text.splitlines())
        return parser
