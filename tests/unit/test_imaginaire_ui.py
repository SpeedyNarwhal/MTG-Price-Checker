from __future__ import annotations

from unittest.mock import MagicMock

from mtg_price_checker.infra.http_client import HttpClientConfig
from mtg_price_checker.infra.imaginaire_ui import (
    human_clear_field,
    human_paste,
    post_deck_builder_via_ui,
    should_use_browser_ui_post,
    submit_and_capture_response,
    wait_for_cf_stable,
    wait_for_deck_builder_results_html,
)


def test_should_use_browser_ui_post_auto_cdp() -> None:
    assert (
        should_use_browser_ui_post(
            browser_ui_post=None,
            browser_cdp_url="http://127.0.0.1:9222",
            browser_only=False,
            browser_headless=True,
        )
        is True
    )


def test_should_use_browser_ui_post_auto_headed_browser_only() -> None:
    assert (
        should_use_browser_ui_post(
            browser_ui_post=None,
            browser_cdp_url=None,
            browser_only=True,
            browser_headless=False,
        )
        is True
    )


def test_should_use_browser_ui_post_explicit_override() -> None:
    assert (
        should_use_browser_ui_post(
            browser_ui_post=False,
            browser_cdp_url="http://127.0.0.1:9222",
            browser_only=True,
            browser_headless=False,
        )
        is False
    )


def test_should_use_browser_ui_post_headless_browser_only_off_by_default() -> None:
    assert (
        should_use_browser_ui_post(
            browser_ui_post=None,
            browser_cdp_url=None,
            browser_only=True,
            browser_headless=True,
        )
        is False
    )


def test_human_paste_uses_clipboard_and_control_v(monkeypatch) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.bounding_box.return_value = {"x": 10, "y": 20, "width": 100, "height": 30}
    page.evaluate.return_value = None

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.write_clipboard",
        lambda _page, _text: True,
    )

    human_paste(page, locator, "$sol ring | $arcane signet", enabled=False)

    page.keyboard.press.assert_any_call("Control+A")
    page.keyboard.press.assert_any_call("Backspace")
    page.keyboard.press.assert_any_call("Control+V")
    page.keyboard.insert_text.assert_not_called()


def test_human_paste_falls_back_to_insert_text_when_clipboard_blocked(monkeypatch) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.bounding_box.return_value = None

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.write_clipboard",
        lambda _page, _text: False,
    )

    human_paste(page, locator, "$sol ring", enabled=False)

    page.keyboard.insert_text.assert_called_once_with("$sol ring")
    assert not any(call.args == ("Control+V",) for call in page.keyboard.press.call_args_list)


def test_human_clear_field_selects_all_and_deletes() -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.bounding_box.return_value = None

    human_clear_field(page, locator)

    page.keyboard.press.assert_any_call("Control+A")
    page.keyboard.press.assert_any_call("Backspace")


def test_wait_for_cf_stable_returns_when_challenge_absent(monkeypatch) -> None:
    page = MagicMock()
    page.url = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"
    page.content.return_value = "<html>deck builder textarea</html>"

    times = iter([0.0, 0.0, 0.1, 3.5, 3.5, 3.5])

    def fake_monotonic() -> float:
        return next(times, 4.0)

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.monotonic", fake_monotonic)
    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.is_cloudflare_challenge_visible",
        lambda _page: False,
    )
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.is_deck_builder_interactive_ready",
        lambda _page: False,
    )

    wait_for_cf_stable(page, stable_seconds=3.0, timeout_seconds=10.0)


def test_wait_for_cf_stable_skips_when_interactive_ready(monkeypatch) -> None:
    page = MagicMock()
    slept = False

    def fake_sleep(_seconds: float) -> None:
        nonlocal slept
        slept = True

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", fake_sleep)
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.is_deck_builder_interactive_ready",
        lambda _page: True,
    )

    wait_for_cf_stable(page, stable_seconds=3.0, timeout_seconds=10.0)

    assert slept is False


def test_submit_and_capture_response_clicks_and_returns_text() -> None:
    page = MagicMock()
    submit = MagicMock()
    submit.bounding_box.return_value = None

    response = MagicMock()
    response.status = 200
    response.text.return_value = '<li class="card-listing">Sol Ring</li>'

    response_info = MagicMock()
    response_info.value = response

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response_info
    context_manager.__exit__.return_value = False
    page.expect_response.return_value = context_manager

    html = submit_and_capture_response(page, submit)

    assert "Sol Ring" in html
    page.expect_response.assert_called_once()


def test_submit_and_capture_response_prefers_dom_when_flag_set(monkeypatch) -> None:
    page = MagicMock()
    submit = MagicMock()
    submit.bounding_box.return_value = None
    dom_html = '<li class="card-listing"><h3 class="magictitle">Sol Ring</h3></li>'

    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.wait_for_deck_builder_results_html",
        lambda _page, timeout_ms=60_000, expected_listing_count=None: dom_html,
    )

    html = submit_and_capture_response(page, submit, prefer_dom_capture=True)

    assert html == dom_html
    page.expect_response.assert_not_called()


def test_submit_and_capture_response_falls_back_to_dom_on_text_failure(monkeypatch) -> None:
    page = MagicMock()
    submit = MagicMock()
    submit.bounding_box.return_value = None
    page.url = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"

    response = MagicMock()
    response.status = 200
    response.text.side_effect = RuntimeError(
        "Protocol error (Network.getResponseBody): No resource with given identifier found"
    )

    response_info = MagicMock()
    response_info.value = response

    context_manager = MagicMock()
    context_manager.__enter__.return_value = response_info
    context_manager.__exit__.return_value = False
    page.expect_response.return_value = context_manager

    dom_html = '<li class="card-listing"><h3 class="magictitle">Sol Ring</h3></li>'
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.wait_for_deck_builder_results_html",
        lambda _page, timeout_ms=60_000, expected_listing_count=None: dom_html,
    )

    html = submit_and_capture_response(page, submit)

    assert html == dom_html


def test_wait_for_deck_builder_results_html_times_out(monkeypatch) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.count.return_value = 0
    page.locator.return_value = locator

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    times = iter([0.0, 100.0])

    def fake_monotonic() -> float:
        return next(times, 100.0)

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.monotonic", fake_monotonic)

    try:
        wait_for_deck_builder_results_html(page, timeout_ms=1000)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "did not appear after submit" in str(exc)

    assert raised


def test_wait_for_deck_builder_results_html_waits_for_expected_count(monkeypatch) -> None:
    page = MagicMock()
    locator = MagicMock()
    counts = iter([1, 2, 3, 3])
    locator.count.side_effect = lambda: next(counts, 3)
    page.locator.return_value = locator

    captured: list[int] = []
    summary_card = """
    <li class="card-listing"><div class="magicdecklist">
      <div class="listinfo">
        <span>1 x Modern Horizons 3 Commander (NM)</span>
        <span>1.00$</span>
      </div>
    </div></li>
    """

    def fake_extract(_page: MagicMock) -> str:
        captured.append(locator.count())
        return summary_card * locator.count()

    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.extract_deck_builder_results_html",
        fake_extract,
    )
    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    times = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

    def fake_monotonic() -> float:
        return next(times, 1.0)

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.monotonic", fake_monotonic)

    html = wait_for_deck_builder_results_html(page, expected_listing_count=3)

    assert "card-listing" in html
    assert captured[-1] == 3


def test_wait_for_deck_builder_results_html_waits_for_summaries(monkeypatch) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.count.return_value = 1
    page.locator.return_value = locator

    extract_calls = 0
    shell_html = '<li class="card-listing"><div class="magicdecklist"></div></li>'
    ready_html = """
    <li class="card-listing"><div class="magicdecklist">
      <div class="listinfo">
        <span>1 x Neon Dynasty Commander (NM)</span>
        <span>0.75$</span>
      </div>
    </div></li>
    """

    def fake_extract(_page: MagicMock) -> str:
        nonlocal extract_calls
        extract_calls += 1
        if extract_calls < 3:
            return shell_html
        return ready_html

    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.extract_deck_builder_results_html",
        fake_extract,
    )
    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    times = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2])

    def fake_monotonic() -> float:
        return next(times, 1.2)

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.monotonic", fake_monotonic)

    html = wait_for_deck_builder_results_html(page, expected_listing_count=1)

    assert "0.75" in html
    assert extract_calls >= 3


def test_wait_for_deck_builder_results_html_raises_when_incomplete(monkeypatch) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.count.side_effect = lambda: 1
    page.locator.return_value = locator

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    times = iter([0.0, 0.1, 0.2, 100.0])

    def fake_monotonic() -> float:
        return next(times, 100.0)

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.monotonic", fake_monotonic)

    try:
        wait_for_deck_builder_results_html(page, timeout_ms=1000, expected_listing_count=3)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "incomplete after submit (1/3 listing(s))" in str(exc)

    assert raised


def test_post_deck_builder_via_ui_pastes_and_submits(monkeypatch) -> None:
    page = MagicMock()
    deck_input = MagicMock()
    submit = MagicMock()

    page.locator.side_effect = lambda selector: MagicMock(
        first=deck_input if "textarea" in selector else submit,
        count=MagicMock(return_value=1),
    )
    deck_input.count.return_value = 1
    submit.count.return_value = 1
    submit.is_visible.return_value = True
    submit.bounding_box.return_value = None
    page.content.return_value = "<html><textarea></textarea></html>"
    page.url = "https://imaginaire.com/fr/magic/constructeur-de-deck.html"

    response = MagicMock()
    response.status = 200
    response.text.return_value = (
        '<li class="card-listing"><h3 class="magictitle">Sol Ring</h3></li>'
    )
    response_info = MagicMock()
    response_info.value = response
    context_manager = MagicMock()
    context_manager.__enter__.return_value = response_info
    context_manager.__exit__.return_value = False
    page.expect_response.return_value = context_manager

    monkeypatch.setattr("mtg_price_checker.infra.imaginaire_ui.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.is_cloudflare_challenge_visible",
        lambda _page: False,
    )
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.find_first_locator",
        lambda _page, _selectors: deck_input,
    )
    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.find_deck_builder_submit_locator",
        lambda _page: submit,
    )
    pasted: list[str] = []

    def capture_paste(_page, _locator, text, *, enabled=True):
        del _page, _locator, enabled
        pasted.append(text)

    monkeypatch.setattr(
        "mtg_price_checker.infra.imaginaire_ui.human_paste",
        capture_paste,
    )

    html = post_deck_builder_via_ui(
        page,
        deck_items_api="$sol ring | $arcane signet",
        ajax_url="https://imaginaire.com/ajax/getDeckBuilder.asp",
        warmup_url=None,
        human_delays=False,
        is_on_deck_builder=True,
        navigate=MagicMock(),
    )

    assert "Sol Ring" in html
    assert pasted == ["sol ring\narcane signet"]


def test_imaginaire_http_client_uses_browser_for_ui_post(monkeypatch) -> None:
    from mtg_price_checker.infra.imaginaire_http_client import ImaginaireHttpClient

    browser = MagicMock()
    browser.can_skip_cloudflare_wait.return_value = True
    browser.post_form.return_value = '<li class="card-listing">Sol Ring</li>'

    client = ImaginaireHttpClient(
        HttpClientConfig(
            browser_cdp_url="http://127.0.0.1:9222",
            browser_ui_post=True,
        )
    )
    monkeypatch.setattr(client, "_browser", browser)

    html = client.post_form(
        "https://imaginaire.com/ajax/getDeckBuilder.asp",
        {"deckItems": "$sol ring"},
    )

    assert "Sol Ring" in html
    browser.post_form.assert_called_once()
