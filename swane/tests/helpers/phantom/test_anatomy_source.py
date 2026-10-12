"""Phantom anatomy resolution: md5-pinned TemplateFlow files, never the network in tests."""

import hashlib

import pytest

from swane.tests.helpers.phantom import anatomy_source as src

TPL_DIR = "tpl-MNI152NLin2009cSym"


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


@pytest.fixture
def fake_tf(tmp_path, monkeypatch):
    """A fake TemplateFlow home plus a fake ``tf.get`` that writes known bytes."""
    home = tmp_path / "templateflow"
    (home / TPL_DIR).mkdir(parents=True)
    payload = {key: ("content-of-" + key).encode() for key in src.ANATOMY_FILES}
    calls = []

    def fake_get(query):
        key = next(k for k, (_n, q) in src.ANATOMY_FILES.items() if q == query)
        calls.append(key)
        path = home / TPL_DIR / src.ANATOMY_FILES[key][0]
        path.write_bytes(payload[key])
        return str(path)

    monkeypatch.setattr(src, "_templateflow_home", lambda: home)
    monkeypatch.setattr(src, "_tf_get", fake_get)
    monkeypatch.setattr(src, "_lock_path", lambda: tmp_path / "fetch.lock")
    monkeypatch.setattr(src, "ANATOMY_MD5", {k: _md5(v) for k, v in payload.items()})
    return home, payload, calls


def test_resolve_fetches_and_verifies(fake_tf):
    home, _payload, calls = fake_tf
    assert not src.anatomy_available()
    files = src.resolve_anatomy_files()
    assert set(files) == set(src.ANATOMY_FILES)
    assert sorted(calls) == sorted(src.ANATOMY_FILES)
    assert src.anatomy_available()


def test_cached_files_are_not_refetched(fake_tf):
    _home, _payload, calls = fake_tf
    src.resolve_anatomy_files()
    calls.clear()
    src.resolve_anatomy_files()
    assert calls == []


def test_unavailable_when_placeholder_is_empty(fake_tf):
    home, _payload, _calls = fake_tf
    src.resolve_anatomy_files()
    (home / TPL_DIR / src.ANATOMY_FILES["gm"][0]).write_bytes(b"")
    assert not src.anatomy_available()


def test_no_download_raises_without_network(fake_tf):
    _home, _payload, calls = fake_tf
    with pytest.raises(RuntimeError, match="TemplateFlow"):
        src.resolve_anatomy_files(allow_download=False)
    assert calls == []


def test_md5_mismatch_is_an_error(fake_tf, monkeypatch):
    pins = dict(src.ANATOMY_MD5, wm="0" * 32)
    monkeypatch.setattr(src, "ANATOMY_MD5", pins)
    with pytest.raises(RuntimeError, match="re-validate"):
        src.resolve_anatomy_files()


def test_fetch_failure_is_wrapped(fake_tf, monkeypatch):
    def boom(_query):
        raise OSError("network unreachable")

    monkeypatch.setattr(src, "_tf_get", boom)
    with pytest.raises(RuntimeError, match="could not fetch .* from TemplateFlow"):
        src.resolve_anatomy_files()
    assert not src.anatomy_available()


def test_fingerprint_depends_on_content_not_location(fake_tf, tmp_path):
    files = src.resolve_anatomy_files()
    copy_dir = tmp_path / "copy"
    copy_dir.mkdir()
    copied = {}
    for key, path in files.items():
        dest = copy_dir / ("x_" + key)
        dest.write_bytes(open(path, "rb").read())
        copied[key] = str(dest)
    assert src.anatomy_fingerprint(files) == src.anatomy_fingerprint(copied)
    open(copied["csf"], "ab").write(b"!")
    assert src.anatomy_fingerprint(files) != src.anatomy_fingerprint(copied)


def test_fetch_runs_under_the_templateflow_lock(fake_tf, monkeypatch):
    events = []

    class RecordingLock:
        def __init__(self, path):
            events.append(("init", path))

        def acquire(self, timeout=None):
            return self

        def __enter__(self):
            events.append(("enter",))
            return self

        def __exit__(self, *exc):
            events.append(("exit",))
            return False

    original = src._tf_get

    def get(query):
        events.append(("get",))
        return original(query)

    monkeypatch.setattr(src, "FileLock", RecordingLock)
    monkeypatch.setattr(src, "_tf_get", get)
    src.resolve_anatomy_files()
    kinds = [e[0] for e in events]
    assert events[0] == ("init", str(src._lock_path()))
    assert kinds.index("enter") < kinds.index("get")
    assert len(kinds) - 1 - kinds[::-1].index("get") < kinds.index("exit")


def test_real_pins_cover_every_file():
    assert set(src.ANATOMY_MD5) == set(src.ANATOMY_FILES)
    assert all(len(v) == 32 for v in src.ANATOMY_MD5.values())


def test_cache_key_depends_on_anatomy_fingerprint(fake_tf, tmp_path):
    from swane.tests.helpers.phantom import dataset

    files = src.resolve_anatomy_files()
    profile = dataset.PhantomProfile()
    key = dataset._cache_key(profile, files)
    assert key == dataset._cache_key(profile, dict(files))
    changed = dict(files)
    alt = tmp_path / "alt_csf"
    alt.write_bytes(b"different anatomy")
    changed["csf"] = str(alt)
    assert dataset._cache_key(profile, changed) != key
