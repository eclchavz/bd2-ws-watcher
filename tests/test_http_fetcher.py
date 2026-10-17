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


def fetcher_with(routes, seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return routes[str(request.url)]()

    return HttpFetcher("bd2-ws-watcher/test", transport=httpx.MockTransport(handler))


def test_robots_txt_server_error_means_disallow_everything():
    seen = []
    fetcher = fetcher_with({"https://store.example/robots.txt": lambda: httpx.Response(503)}, seen)
    with pytest.raises(RobotsDisallowed):
        fetcher.get_json("https://store.example/products.json")
    assert seen == ["https://store.example/robots.txt"]


def test_redirect_targets_are_checked_against_their_own_robots_txt():
    seen = []
    fetcher = fetcher_with(
        {
            "https://store.example/robots.txt": lambda: httpx.Response(404),
            "https://store.example/products.json": lambda: httpx.Response(
                301, headers={"location": "https://cdn.example/products.json"}
            ),
            "https://cdn.example/robots.txt": lambda: httpx.Response(200, text="User-agent: *\nDisallow: /\n"),
        },
        seen,
    )
    with pytest.raises(RobotsDisallowed):
        fetcher.get_json("https://store.example/products.json")
    assert "https://cdn.example/products.json" not in seen


def test_robots_txt_is_read_again_after_a_day():
    seen = []
    clock = [0.0]
    fetcher = make_fetcher(seen)
    fetcher.clock = lambda: clock[0]
    fetcher.get_json("https://store.example/a.json")
    clock[0] += 24 * 3600 + 1
    fetcher.get_json("https://store.example/b.json")
    assert [r.url.path for r in seen] == ["/robots.txt", "/a.json", "/robots.txt", "/b.json"]
