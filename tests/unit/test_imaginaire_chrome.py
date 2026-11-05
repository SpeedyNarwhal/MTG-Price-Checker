from mtg_price_checker.app import imaginaire_chrome
from mtg_price_checker.app.imaginaire_chrome import (
    cdp_status,
    close_managed_chrome,
    default_cdp_url,
    ensure_chrome_for_imaginaire,
)


def test_default_cdp_url() -> None:
    assert default_cdp_url() == "http://127.0.0.1:9222"


def test_cdp_status_unreachable() -> None:
    status = cdp_status("http://127.0.0.1:1")
    assert status["reachable"] is False
    assert "error" in status


def test_ensure_chrome_reuses_reachable_cdp(monkeypatch) -> None:
    monkeypatch.setattr(
        imaginaire_chrome,
        "cdp_status",
        lambda cdp_url="http://127.0.0.1:9222": {
            "reachable": True,
            "cdp_url": cdp_url,
            "browser": "Chrome/test",
        },
    )

    def fail_launch(**_kwargs: object) -> dict[str, object]:
        raise AssertionError("should not launch")

    monkeypatch.setattr(imaginaire_chrome, "launch_chrome_for_imaginaire", fail_launch)

    session = ensure_chrome_for_imaginaire()
    assert session.launched_by_app is False
    assert session.cdp_url == "http://127.0.0.1:9222"


def test_close_managed_chrome_noop_without_process() -> None:
    result = close_managed_chrome()
    assert result["closed"] is False
    assert result["reason"] == "no_managed_chrome"
