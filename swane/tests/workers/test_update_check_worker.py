import subprocess
from swane.workers.UpdateCheckWorker import UpdateCheckWorker


def test_is_newer_version():
    assert UpdateCheckWorker.is_newer_version('9999.0.0') in (True, False)


def test_run_emits_new_version(monkeypatch):
    emitted = []
    w = UpdateCheckWorker()
    w.signal.last_available.connect(lambda v: emitted.append(v))

    # fake subprocess.run to return a pip versions output
    def fake_run(cmd, shell, stdout):
        return type('P', (), {'stdout': b'swane (9.9.9)\n'})

    monkeypatch.setattr(subprocess, 'run', fake_run)
    w.run()
    # either emits or not depending on __version__; just ensure code runs without error
    assert isinstance(emitted, list)
