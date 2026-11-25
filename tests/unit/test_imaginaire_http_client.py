from unittest.mock import MagicMock

from mtg_price_checker.infra.browser_http_client import (
    BrowserHttpClient,
    has_cf_clearance_cookie,
    is_cloudflare_challenge_visible,
    is_cloudflare_challenge_visible_in_html,
    is_deck_builder_interactive_ready,
    is_deck_builder_ready_in_html,
    is_imaginaire_session_ready,
    is_navigation_race_error,
    is_successful_deck_builder_response,
    playwright_cookies_from_file,
    safe_page_content,
    should_skip_browser_cookie,
)
from mtg_price_checker.infra.http_client import HttpClientConfig
from mtg_price_checker.infra.imaginaire_http_client import ImaginaireHttpClient


class FakeBrowserClient:
    def __init__(self, html: str) -> None:
        self.html = html
        self.ensure_calls: list[str | None] = []
        self.post_form_calls: list[tuple[str, dict[str, str]]] = []
        self.closed = False
        self.can_skip = False

    def ensure_cloudflare_cleared(
        self,
        warmup_url: str | None = None,
        *,
        status_callback=None,
    ) -> None:
        del status_callback
        self.ensure_calls.append(warmup_url)

    def post_form(
        self,
        url: str,
        data: dict[str, str],
        *,
        referer: str | None = None,
    ) -> str:
        del referer
        self.post_form_calls.append((url, data))
        return self.html

    def can_skip_cloudflare_wait(self) -> bool:
        return self.can_skip

    def get_context_cookies(self) -> list[dict[str, str]]:
        return [{"name": "cf_clearance", "value": "test", "domain": ".imaginaire.com"}]

    def close(self) -> None:
        self.closed = True


def test_imaginaire_skips_cloudflare_wait_when_cdp_ready(monkeypatch) -> None:
    browser = FakeBrowserClient(html="<html><li class='card-listing'>Sol Ring</li></html>")
    browser.can_skip = True

    client = ImaginaireHttpClient(HttpClientConfig(browser_cdp_url="http://127.0.0.1:9222"))
    monkeypatch.setattr(client, "_browser", browser)

    html = client.post_form(
        "https://imaginaire.com/ajax/getDeckBuilder.asp",
        {"deckItems": "$sol ring"},
    )

    assert "Sol Ring" in html
    assert browser.ensure_calls == []


def test_imaginaire_http_client_always_uses_browser(monkeypatch) -> None:
    browser = FakeBrowserClient(html="<html>Arcane Signet</html>")

    client = ImaginaireHttpClient()
    monkeypatch.setattr(client, "_browser", browser)

    html = client.post_form(
        "https://imaginaire.com/ajax/getDeckBuilder.asp",
        {"deckItems": "$arcane signet"},
        referer="https://imaginaire.com/fr/magic/constructeur-de-deck.html",
    )

    assert "Arcane Signet" in html
    assert browser.ensure_calls == ["https://imaginaire.com/fr/magic/constructeur-de-deck.html"]
    assert len(browser.post_form_calls) == 1

    client.close()
    assert browser.closed is True


def test_cloudflare_challenge_visible_in_html() -> None:
    assert is_cloudflare_challenge_visible_in_html("Chargement en cours")
    assert is_cloudflare_challenge_visible_in_html("Verify you are human")
    assert not is_cloudflare_challenge_visible_in_html("<html>deck builder</html>")


def test_deck_builder_ready_in_html() -> None:
    assert is_deck_builder_ready_in_html("<textarea></textarea>")
    assert is_deck_builder_ready_in_html('<input name="deckItems">')
    assert is_deck_builder_ready_in_html("Constructeur de deck")


def test_successful_deck_builder_response() -> None:
    assert is_successful_deck_builder_response('<li class="card-listing">')
    assert not is_successful_deck_builder_response("<html>error</html>")


def test_has_cf_clearance_cookie() -> None:
    assert has_cf_clearance_cookie([{"name": "cf_clearance", "value": "x"}])
    assert not has_cf_clearance_cookie([{"name": "langd", "value": "fr"}])


def test_playwright_cookies_from_file_skips_cloudflare_cookies(tmp_path) -> None:
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                "imaginaire.com\tFALSE\t/\tFALSE\t1797284698\tlangd\tfr",
                ".imaginaire.com\tTRUE\t/\tTRUE\t1797284695\tcf_clearance\tabc",
                ".imaginaire.com\tTRUE\t/\tTRUE\t1797284695\t__cf_bm\tdef",
            ]
        ),
        encoding="utf-8",
    )

    cookies, skipped = playwright_cookies_from_file(cookies_file)

    assert skipped == 2
    assert len(cookies) == 1
    assert cookies[0]["name"] == "langd"
    assert cookies[0]["url"] == "https://imaginaire.com"


def test_should_skip_browser_cookie_names() -> None:
    from http.cookiejar import Cookie

    cf = Cookie(
        version=0,
        name="cf_clearance",
        value="x",
        port=None,
        port_specified=False,
        domain=".imaginaire.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )
    lang = Cookie(
        version=0,
        name="langd",
        value="fr",
        port=None,
        port_specified=False,
        domain="imaginaire.com",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )

    assert should_skip_browser_cookie(cf)
    assert not should_skip_browser_cookie(lang)


def _mock_locator(*, count: int = 1, visible: bool = False) -> MagicMock:
    locator = MagicMock()
    locator.count.return_value = count
    locator.is_visible.return_value = visible
    return locator


def test_hidden_turnstile_not_treated_as_challenge() -> None:
    page = MagicMock()
    page.content.return_value = "<html><div id='cf-turnstile'></div></html>"

    def locator_side_effect(selector: str) -> MagicMock:
        wrapper = MagicMock()
        if selector in ("#cf-turnstile", ".cf-turnstile"):
            wrapper.first = _mock_locator(count=1, visible=False)
        elif selector == "#send2":
            wrapper.first = _mock_locator(count=0, visible=False)
        elif "textarea" in selector or "deckItems" in selector:
            wrapper.first = _mock_locator(count=0, visible=False)
        else:
            wrapper.first = _mock_locator(count=0, visible=False)
        return wrapper

    page.locator.side_effect = locator_side_effect

    assert not is_cloudflare_challenge_visible(page)


def test_interactive_ready_overrides_dormant_cf_markup() -> None:
    page = MagicMock()
    page.content.return_value = "Verify you are human <textarea></textarea>"

    def locator_side_effect(selector: str) -> MagicMock:
        wrapper = MagicMock()
        if selector == "textarea":
            wrapper.first = _mock_locator(count=1, visible=True)
        elif selector == "#send2":
            wrapper.first = _mock_locator(count=1, visible=True)
        elif selector in ("#cf-turnstile", ".cf-turnstile"):
            wrapper.first = _mock_locator(count=1, visible=False)
        elif "challenges.cloudflare" in selector:
            wrapper.first = _mock_locator(count=0, visible=False)
        else:
            wrapper.first = _mock_locator(count=0, visible=False)
        return wrapper

    page.locator.side_effect = locator_side_effect

    assert is_deck_builder_interactive_ready(page)
    assert not is_cloudflare_challenge_visible(page)
    assert is_imaginaire_session_ready(page)


def test_visible_turnstile_counts_as_challenge_even_when_deck_ui_ready() -> None:
    page = MagicMock()
    page.content.return_value = "<html><textarea></textarea><div id='cf-turnstile'></div></html>"

    def locator_side_effect(selector: str) -> MagicMock:
        wrapper = MagicMock()
        if selector == "textarea":
            wrapper.first = _mock_locator(count=1, visible=True)
        elif selector == "#send2":
            wrapper.first = _mock_locator(count=1, visible=True)
        elif selector in ("#cf-turnstile", ".cf-turnstile"):
            wrapper.first = _mock_locator(count=1, visible=True)
        else:
            wrapper.first = _mock_locator(count=0, visible=False)
        return wrapper

    page.locator.side_effect = locator_side_effect

    assert is_deck_builder_interactive_ready(page)
    assert is_cloudflare_challenge_visible(page)
    assert not is_imaginaire_session_ready(page)


def test_is_navigation_race_error_detects_playwright_message() -> None:
    assert is_navigation_race_error(
        RuntimeError(
            "Unable to retrieve content because the page is navigating and changing the content."
        )
    )
    assert not is_navigation_race_error(RuntimeError("connection closed"))


def test_safe_page_content_retries_through_navigation_race(monkeypatch) -> None:
    page = MagicMock()
    page.content.side_effect = [
        RuntimeError(
            "Unable to retrieve content because the page is navigating and changing the content."
        ),
        "<html>ready</html>",
    ]
    page.wait_for_load_state = MagicMock()
    monkeypatch.setattr(
        "mtg_price_checker.infra.browser_http_client.time.sleep",
        lambda _s: None,
    )

    assert safe_page_content(page) == "<html>ready</html>"
    page.wait_for_load_state.assert_called()


def test_wait_continues_when_page_navigates_after_captcha(monkeypatch) -> None:
    client = BrowserHttpClient(HttpClientConfig(browser_cdp_url="http://127.0.0.1:9222"))
    client._page = MagicMock()
    client._context = MagicMock()
    statuses: list[str] = []
    calls = {"n": 0}

    def fake_ready() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(
                "Unable to retrieve content because the page is navigating and changing the content."
            )
        return calls["n"] >= 3

    monkeypatch.setattr(client, "_is_imaginaire_session_ready", fake_ready)
    monkeypatch.setattr(client, "_invalidate_stale_cloudflare_cookies_if_needed", lambda: None)
    monkeypatch.setattr(client, "_cloudflare_status_message", lambda: "status: waiting")
    monkeypatch.setattr(
        "mtg_price_checker.infra.browser_http_client.time.sleep",
        lambda _s: None,
    )
    monkeypatch.setattr(
        "mtg_price_checker.infra.browser_http_client._wait_for_dom_settle",
        lambda _page, **_k: None,
    )

    client._wait_until_imaginaire_ready(
        timeout_seconds=30,
        status_callback=statuses.append,
        require_cf_clearance=False,
    )

    assert calls["n"] >= 3
    assert any("navigating" in message.lower() for message in statuses)


def test_cdp_cloudflare_wait_polls_until_ready_without_input(monkeypatch) -> None:
    client = BrowserHttpClient(HttpClientConfig(browser_cdp_url="http://127.0.0.1:9222"))
    client._page = MagicMock()
    client._page.url = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"
    client._context = MagicMock()
    client._uses_cdp = True
    client._ensure_page = MagicMock()

    ready_after = {"n": 0}
    statuses: list[str] = []

    def fake_ready() -> bool:
        ready_after["n"] += 1
        return ready_after["n"] >= 3

    monkeypatch.setattr(client, "_is_imaginaire_session_ready", fake_ready)
    monkeypatch.setattr(client, "_invalidate_stale_cloudflare_cookies_if_needed", lambda: None)
    monkeypatch.setattr(client, "_cloudflare_status_message", lambda: "status: waiting")
    monkeypatch.setattr(
        "mtg_price_checker.infra.browser_http_client.time.sleep",
        lambda _s: None,
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("input() must not be called")),
    )

    client.ensure_cloudflare_cleared(
        "https://imaginaire.com/fr/magic/constructeur-de-deck.html",
        status_callback=statuses.append,
    )

    assert client._cloudflare_cleared is True
    assert ready_after["n"] >= 3
    assert any("waiting" in message.lower() or "solve" in message.lower() for message in statuses)
    assert "input()" not in " ".join(statuses)


def test_is_deck_builder_interactive_ready_requires_visible_input_and_send2() -> None:
    page = MagicMock()
    textarea = _mock_locator(count=1, visible=True)
    send2 = _mock_locator(count=1, visible=True)

    def locator_side_effect(selector: str) -> MagicMock:
        wrapper = MagicMock()
        if selector == "textarea":
            wrapper.first = textarea
        elif selector == "#send2":
            wrapper.first = send2
        else:
            wrapper.first = _mock_locator(count=0, visible=False)
        return wrapper

    page.locator.side_effect = locator_side_effect

    assert is_deck_builder_interactive_ready(page)

    send2.is_visible.return_value = False
    assert not is_deck_builder_interactive_ready(page)


def test_cdp_mode_does_not_clear_cloudflare_cookies() -> None:
    client = BrowserHttpClient(HttpClientConfig(browser_cdp_url="http://127.0.0.1:9222"))
    client._uses_cdp = True
    client._page = MagicMock()
    client._context = MagicMock()
    client._context.cookies.return_value = [{"name": "cf_clearance", "value": "x"}]
    client._clear_cloudflare_cookies = MagicMock()

    client._invalidate_stale_cloudflare_cookies_if_needed()

    client._clear_cloudflare_cookies.assert_not_called()
