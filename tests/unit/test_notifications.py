import sys
import types

from mtg_price_checker.app import notifications


def test_notify_job_finished_does_not_raise_without_winotify(monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "winotify" or name.startswith("winotify."):
            raise ImportError("no winotify")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    notifications.notify_job_finished(title="Done", message="Finished 3 cards.")


def test_notify_job_finished_calls_winotify_on_windows(monkeypatch) -> None:
    shown: list[object] = []

    class FakeAudio:
        Default = object()

    class FakeNotification:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def set_audio(self, *_args: object, **_kwargs: object) -> None:
            return None

        def show(self) -> None:
            shown.append(self)

    fake_mod = types.ModuleType("winotify")
    fake_mod.Notification = FakeNotification  # type: ignore[attr-defined]
    fake_mod.audio = FakeAudio  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "winotify", fake_mod)
    monkeypatch.setattr(notifications.sys, "platform", "win32")

    notifications.notify_job_finished(title="Price check complete", message="Finished 3 cards.")
    assert len(shown) == 1
    assert shown[0].kwargs["title"] == "Price check complete"  # type: ignore[attr-defined]
