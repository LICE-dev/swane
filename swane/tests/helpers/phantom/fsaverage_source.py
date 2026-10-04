"""Locate the two fsaverage segmentations the phantom anatomy is built from.

The phantom reads only ``fsaverage/mri/aseg.mgz`` and ``aparc+aseg.mgz``.
They come from ``$FREESURFER_HOME/subjects/fsaverage`` when FreeSurfer is
installed; otherwise they are downloaded at runtime from the fsaverage archive
MNE-Python mirrors (``mne-tools/mne-data``, release ``fsaverage-1.0``), pinned
by md5. The mirrored files were verified byte-identical to FreeSurfer 8.2's.

License: these are FreeSurfer data, distributed under the FreeSurfer Software
License (https://github.com/freesurfer/freesurfer/blob/dev/LICENSE.txt); the
mirror repository's own license does not change that. SWANe only fetches them
to build a local phantom: they are never committed, packaged or uploaded.
"""

import hashlib
import os
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
import zipfile

FSAVERAGE_FILES = ("aseg.mgz", "aparc+aseg.mgz")
MNE_FSAVERAGE_URL = (
    "https://github.com/mne-tools/mne-data/releases/download/"
    "fsaverage-1.0/fsaverage-root.zip"
)
MNE_FSAVERAGE_MD5 = "5133fe92b7b8f03ae19219d5f46e4177"
DEFAULT_CACHE_DIR = os.path.join(
    os.path.expanduser("~"), ".cache", "swane", "fsaverage", "mri"
)
_DOWNLOAD_TIMEOUT_S = 600


def _has_files(mri_dir: str) -> bool:
    return bool(mri_dir) and all(
        os.path.isfile(os.path.join(mri_dir, name)) for name in FSAVERAGE_FILES
    )


def freesurfer_fsaverage_mri_dir(freesurfer_home: str | None = None) -> str:
    """Return ``<FREESURFER_HOME>/subjects/fsaverage/mri`` if usable, else ""."""
    home = freesurfer_home or os.environ.get("FREESURFER_HOME") or ""
    path = os.path.join(home, "subjects", "fsaverage", "mri") if home else ""
    return path if _has_files(path) else ""


def fsaverage_available(
    freesurfer_home: str | None = None, cache_dir: str | None = None
) -> bool:
    """True when the files are on disk already (never touches the network)."""
    return bool(freesurfer_fsaverage_mri_dir(freesurfer_home)) or _has_files(
        cache_dir or DEFAULT_CACHE_DIR
    )


def _md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _ssl_context():
    # python.org macOS builds ship without CA certificates (see
    # swane.utils.antspynet_weights): prefer certifi's bundle when present.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def download_fsaverage_mri(
    cache_dir: str | None = None,
    url: str = MNE_FSAVERAGE_URL,
    md5: str = MNE_FSAVERAGE_MD5,
) -> str:
    """Download the mirror archive, verify it, keep only the two segmentations."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if _has_files(cache_dir):
        return cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    handle, tmp_zip = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(cache_dir))
    os.close(handle)
    try:
        try:
            with urllib.request.urlopen(
                url, timeout=_DOWNLOAD_TIMEOUT_S, context=_ssl_context()
            ) as response, open(tmp_zip, "wb") as out:
                shutil.copyfileobj(response, out)
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(
                "could not download the fsaverage archive from %s (cache dir %s): %s"
                % (url, cache_dir, exc)
            ) from exc
        got = _md5(tmp_zip)
        if got != md5:
            raise RuntimeError(
                "fsaverage archive md5 mismatch: expected %s, got %s (%s)"
                % (md5, got, url)
            )
        try:
            with zipfile.ZipFile(tmp_zip) as archive:
                for name in FSAVERAGE_FILES:
                    staging = os.path.join(cache_dir, name + ".part")
                    with archive.open("fsaverage/mri/" + name) as src, open(
                        staging, "wb"
                    ) as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(staging, os.path.join(cache_dir, name))
        except KeyError as exc:
            raise RuntimeError(
                "fsaverage archive from %s lacks %s (cache dir %s)"
                % (url, exc, cache_dir)
            ) from exc
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)
    return cache_dir


def resolve_fsaverage_mri_dir(
    freesurfer_home: str | None = None,
    allow_download: bool = True,
    cache_dir: str | None = None,
) -> str:
    """Return a folder holding both segmentations, downloading them if needed."""
    local = freesurfer_fsaverage_mri_dir(freesurfer_home)
    if local:
        return local
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if _has_files(cache_dir):
        return cache_dir
    if not allow_download:
        raise RuntimeError(
            "fsaverage not found: install FreeSurfer (set FREESURFER_HOME) or "
            "allow the download of the MNE fsaverage mirror into %s" % cache_dir
        )
    return download_fsaverage_mri(cache_dir)


def fsaverage_fingerprint(mri_dir: str) -> str:
    """md5 over both segmentations: identifies the anatomy, not its location."""
    digest = hashlib.md5()
    for name in FSAVERAGE_FILES:
        digest.update(_md5(os.path.join(mri_dir, name)).encode())
    return digest.hexdigest()
