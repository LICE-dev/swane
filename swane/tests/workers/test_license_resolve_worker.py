from threading import Barrier

import swane.workers.LicenseResolveWorker as mod
from swane.utils.license_consent import ResolvedLicense, LicenseSource


def test_worker_resolves_all_tools_and_emits(monkeypatch):
    def fake_resolve(info, context, timeout):
        return ResolvedLicense(
            info.tool_id, info.display_name, "TEXT", False, LicenseSource.BUNDLED
        )

    monkeypatch.setattr(mod, "resolve_license_text", fake_resolve)

    worker = mod.LicenseResolveWorker(["fsl", "freesurfer"], {"slicer_path": ""})
    captured = []
    worker.signal.resolved.connect(lambda resolved: captured.append(resolved))

    worker.run()

    assert len(captured) == 1
    assert [rl.tool_id for rl in captured[0]] == ["fsl", "freesurfer"]


def test_worker_resolves_tools_concurrently(monkeypatch):
    both_started = Barrier(2)

    def fake_resolve(info, context, timeout):
        both_started.wait(timeout=1)
        return ResolvedLicense(
            info.tool_id, info.display_name, "TEXT", False, LicenseSource.BUNDLED
        )

    monkeypatch.setattr(mod, "resolve_license_text", fake_resolve)

    worker = mod.LicenseResolveWorker(["fsl", "freesurfer"], {})
    captured = []
    failed = []
    worker.signal.resolved.connect(captured.append)
    worker.signal.failed.connect(failed.append)

    worker.run()

    assert not failed
    assert [rl.tool_id for rl in captured[0]] == ["fsl", "freesurfer"]


def test_worker_emits_failure_and_terminal_signal(monkeypatch):
    def fail_resolve(info, context, timeout):
        raise OSError("synthetic license failure")

    monkeypatch.setattr(mod, "resolve_license_text", fail_resolve)

    worker = mod.LicenseResolveWorker(["fsl"], {})
    resolved = []
    failed = []
    finished = []
    worker.signal.resolved.connect(resolved.append)
    worker.signal.failed.connect(failed.append)
    worker.signal.finished.connect(lambda: finished.append(True))

    worker.run()

    assert not resolved
    assert failed == ["synthetic license failure"]
    assert finished == [True]


def test_worker_uses_short_network_timeout():
    worker = mod.LicenseResolveWorker(["fsl"], {})
    assert worker.timeout == mod.DEFAULT_LICENSE_FETCH_TIMEOUT == 3.0
