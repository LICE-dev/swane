"""fsaverage resolution: FreeSurfer first, then the md5-pinned MNE mirror."""

import hashlib
import io
import zipfile

import pytest

from swane.tests.helpers.phantom import fsaverage_source as fs


def _zip_bytes(extra=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("fsaverage/mri/aseg.mgz", b"aseg-bytes")
        archive.writestr("fsaverage/mri/aparc+aseg.mgz", b"aparc-bytes")
        if extra:
            archive.writestr("fsaverage/mri/T1.mgz", b"not wanted")
    return buf.getvalue()


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen(payload, calls):
    def urlopen(url, timeout=None, context=None):
        calls.append(url)
        return _Response(payload)

    return urlopen


def test_freesurfer_install_wins(tmp_path, monkeypatch):
    mri = tmp_path / "fs" / "subjects" / "fsaverage" / "mri"
    mri.mkdir(parents=True)
    for name in fs.FSAVERAGE_FILES:
        (mri / name).write_bytes(b"x")
    calls = []
    monkeypatch.setattr(fs.urllib.request, "urlopen", _fake_urlopen(b"", calls))
    got = fs.resolve_fsaverage_mri_dir(
        freesurfer_home=str(tmp_path / "fs"), cache_dir=str(tmp_path / "cache")
    )
    assert got == str(mri)
    assert calls == []


def test_download_extracts_only_the_two_files(tmp_path, monkeypatch):
    payload = _zip_bytes()
    calls = []
    monkeypatch.setattr(fs.urllib.request, "urlopen", _fake_urlopen(payload, calls))
    cache = tmp_path / "cache" / "mri"
    got = fs.download_fsaverage_mri(
        cache_dir=str(cache), md5=hashlib.md5(payload).hexdigest()
    )
    assert got == str(cache)
    assert sorted(p.name for p in cache.iterdir()) == sorted(fs.FSAVERAGE_FILES)
    assert (cache / "aseg.mgz").read_bytes() == b"aseg-bytes"
    assert list((cache.parent).glob("*.zip")) == []
    assert len(calls) == 1
    # Second resolution uses the cache, no network.
    assert fs.resolve_fsaverage_mri_dir(
        freesurfer_home=str(tmp_path / "nofs"), cache_dir=str(cache)
    ) == str(cache)
    assert len(calls) == 1


def test_md5_mismatch_leaves_no_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        fs.urllib.request, "urlopen", _fake_urlopen(_zip_bytes(), calls)
    )
    cache = tmp_path / "cache" / "mri"
    with pytest.raises(RuntimeError, match="md5"):
        fs.download_fsaverage_mri(cache_dir=str(cache), md5="0" * 32)
    assert not fs.fsaverage_available(
        freesurfer_home=str(tmp_path / "nofs"), cache_dir=str(cache)
    )


def test_no_download_allowed_raises_clearly(tmp_path):
    with pytest.raises(RuntimeError, match="fsaverage"):
        fs.resolve_fsaverage_mri_dir(
            freesurfer_home=str(tmp_path / "nofs"),
            allow_download=False,
            cache_dir=str(tmp_path / "cache"),
        )


def test_fingerprint_depends_on_content_not_location(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        (d / "aseg.mgz").write_bytes(b"1")
        (d / "aparc+aseg.mgz").write_bytes(b"2")
    assert fs.fsaverage_fingerprint(str(a)) == fs.fsaverage_fingerprint(str(b))
    (b / "aseg.mgz").write_bytes(b"3")
    assert fs.fsaverage_fingerprint(str(a)) != fs.fsaverage_fingerprint(str(b))


def test_network_error_becomes_runtime_error_naming_url(tmp_path, monkeypatch):
    url = "https://example.invalid/fsaverage-root.zip"

    def urlopen(u, timeout=None, context=None):
        raise fs.urllib.error.URLError("offline")

    monkeypatch.setattr(fs.urllib.request, "urlopen", urlopen)
    cache = tmp_path / "cache" / "mri"
    with pytest.raises(RuntimeError) as excinfo:
        fs.download_fsaverage_mri(cache_dir=str(cache), url=url)
    assert url in str(excinfo.value)
    assert str(cache) in str(excinfo.value)
    assert not fs.fsaverage_available(
        freesurfer_home=str(tmp_path / "nofs"), cache_dir=str(cache)
    )


def test_archive_missing_member_becomes_runtime_error(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("fsaverage/mri/aseg.mgz", b"aseg-bytes")
    payload = buf.getvalue()
    monkeypatch.setattr(fs.urllib.request, "urlopen", _fake_urlopen(payload, []))
    cache = tmp_path / "cache" / "mri"
    with pytest.raises(RuntimeError, match="aparc"):
        fs.download_fsaverage_mri(
            cache_dir=str(cache), md5=hashlib.md5(payload).hexdigest()
        )
    assert not fs.fsaverage_available(
        freesurfer_home=str(tmp_path / "nofs"), cache_dir=str(cache)
    )


def test_partial_cache_is_not_available_and_download_completes_it(
    tmp_path, monkeypatch
):
    payload = _zip_bytes()
    cache = tmp_path / "cache" / "mri"
    cache.mkdir(parents=True)
    (cache / "aseg.mgz").write_bytes(b"aseg-bytes")
    (cache / "aparc+aseg.mgz.part").write_bytes(b"stale")
    nofs = str(tmp_path / "nofs")
    assert not fs.fsaverage_available(freesurfer_home=nofs, cache_dir=str(cache))

    monkeypatch.setattr(fs.urllib.request, "urlopen", _fake_urlopen(payload, []))
    got = fs.download_fsaverage_mri(
        cache_dir=str(cache), md5=hashlib.md5(payload).hexdigest()
    )
    assert got == str(cache)
    assert fs.fsaverage_available(freesurfer_home=nofs, cache_dir=str(cache))
    assert (cache / "aparc+aseg.mgz").read_bytes() == b"aparc-bytes"
    assert not (cache / "aparc+aseg.mgz.part").exists()
