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
