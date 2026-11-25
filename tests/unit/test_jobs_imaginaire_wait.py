from unittest.mock import MagicMock

from mtg_price_checker.app.jobs import Job, JobManager, JobStatus


def test_wait_for_imaginaire_cloudflare_emits_status_and_calls_ensure() -> None:
    manager = JobManager()
    job = Job(
        job_id="job-1",
        status=JobStatus.RUNNING,
        stores=["imaginaire", "facetoface"],
        min_condition="NM",
        decklist="Sol Ring",
        browser_cdp_url="http://127.0.0.1:9222",
        created_at="2026-01-01T00:00:00+00:00",
    )

    http_client = MagicMock()
    store = MagicMock()
    store.store_id = "imaginaire"
    store._http_client = http_client

    manager._wait_for_imaginaire_cloudflare(job, [store])

    http_client.ensure_cloudflare_cleared.assert_called_once()
    kwargs = http_client.ensure_cloudflare_cleared.call_args.kwargs
    assert "status_callback" in kwargs

    kwargs["status_callback"]("status: Cloudflare challenge visible")
    assert job.message == "status: Cloudflare challenge visible"

    events = []
    while not job.events.empty():
        events.append(job.events.get_nowait())
    assert any(event.get("type") == "status" for event in events)


def test_wait_for_imaginaire_cloudflare_skips_when_store_missing() -> None:
    manager = JobManager()
    job = Job(
        job_id="job-2",
        status=JobStatus.RUNNING,
        stores=["facetoface"],
        min_condition="NM",
        decklist="Sol Ring",
        browser_cdp_url=None,
        created_at="2026-01-01T00:00:00+00:00",
    )
    store = MagicMock()
    store.store_id = "facetoface"

    manager._wait_for_imaginaire_cloudflare(job, [store])

    assert job.events.empty()
