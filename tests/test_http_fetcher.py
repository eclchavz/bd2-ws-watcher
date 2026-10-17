import httpx
import pytest

from bd2watcher.fetcher import HttpFetcher, RobotsDisallowed

ROBOTS = "User-agent: *\nDisallow: /checkout\nDisallow: /private\n"


def make_fetcher(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(200, json={"products": []})

    return HttpFetcher("bd2-ws-watcher/test", transport=httpx.MockTransport(handler))


def test_requests_identify_the_app_and_return_json():
    seen = []
    assert make_fetcher(seen).get_json("https://store.example/products.json?page=1") == {"products": []}
    assert all(r.headers["user-agent"] == "bd2-ws-watcher/test" for r in seen)


def test_urls_disallowed_by_robots_txt_are_never_requested():
    seen = []
    with pytest.raises(RobotsDisallowed):
        make_fetcher(seen).get_json("https://store.example/private/products.json")
    assert [r.url.path for r in seen] == ["/robots.txt"]


def test_robots_txt_is_read_once_per_host():
    seen = []
    fetcher = make_fetcher(seen)
    fetcher.get_json("https://store.example/a.json")
    fetcher.get_json("https://store.example/b.json")
    assert [r.url.path for r in seen] == ["/robots.txt", "/a.json", "/b.json"]
