"""Fetch the files the phantom anatomy is built from: CerebrA + ICBM 2009c Sym.

The phantom reads six files of the ``tpl-MNI152NLin2009cSym`` TemplateFlow
template (1 mm, RAS): the CerebrA label map and its label table, the GM/WM/CSF
probabilistic segmentations and the brain mask. They are fetched at run time
into the TemplateFlow cache (``$TEMPLATEFLOW_HOME``, by default
``~/.cache/templateflow``) and pinned by md5, so an upstream revision cannot
silently change the phantom and the pre-release margins measured on it.

Licenses: CerebrA is CC0 1.0 (its labels derive from Mindboggle-101, CC BY
4.0); the ICBM 2009c Nonlinear Symmetric files carry the McConnell Brain
Imaging Centre notice. See NOTICE.md. SWANe only fetches them to build a local
phantom: they are never committed, packaged or uploaded.
"""

import hashlib
import os
from pathlib import Path

from filelock import FileLock

TEMPLATE = "MNI152NLin2009cSym"

#: key -> (file name inside the template folder, TemplateFlow query).
#: The label table really is ``atlas-CerebA`` upstream (sic), while the label
#: map is ``atlas-CerebrA``.
ANATOMY_FILES = {
    "cerebra": (
        "tpl-MNI152NLin2009cSym_res-1_atlas-CerebrA_dseg.nii.gz",
        dict(resolution=1, atlas="CerebrA", suffix="dseg", extension=".nii.gz"),
    ),
    "tsv": (
        "tpl-MNI152NLin2009cSym_atlas-CerebA_dseg.tsv",
        dict(atlas="CerebA", suffix="dseg", extension=".tsv"),
    ),
    "gm": (
        "tpl-MNI152NLin2009cSym_res-1_label-GM_probseg.nii.gz",
        dict(resolution=1, label="GM", suffix="probseg"),
    ),
    "wm": (
        "tpl-MNI152NLin2009cSym_res-1_label-WM_probseg.nii.gz",
        dict(resolution=1, label="WM", suffix="probseg"),
    ),
    "csf": (
        "tpl-MNI152NLin2009cSym_res-1_label-CSF_probseg.nii.gz",
        dict(resolution=1, label="CSF", suffix="probseg"),
    ),
    "mask": (
        "tpl-MNI152NLin2009cSym_res-1_desc-brain_mask.nii.gz",
        dict(resolution=1, desc="brain", suffix="mask"),
    ),
}

#: md5 of each file as published by TemplateFlow (measured 2026-10-12).
#: A mismatch that survives a re-fetch means the upstream anatomy changed:
#: re-validate the pre-release sweep on the new files, then update these pins.
ANATOMY_MD5 = {
    "cerebra": "7b69ad2478c6be7de12bb5b254b4cb7c",
    "tsv": "d0d4df1f90209fd0ebdf31355c89c780",
    "gm": "e65772ab469f7ce29206d9c87b0600da",
    "wm": "e5f636592b9c3a3eea4660ebc987a385",
    "csf": "88dfca50b0a4acad1ee1b61fdbbec718",
    "mask": "6d6a792e858b7056cf27435aab17169d",
}

_LOCK_TIMEOUT_SECONDS = 3600


def _templateflow_home() -> Path:
    from templateflow import conf

    return Path(conf.TF_HOME)


def _tf_get(query: dict) -> str:
    import templateflow.api as tf

    found = tf.get(TEMPLATE, **query)
    if isinstance(found, list):
        if len(found) != 1:
            raise RuntimeError(
                "TemplateFlow returned %d files for %s %s"
                % (len(found), TEMPLATE, query)
            )
        found = found[0]
    return str(found)


def _lock_path() -> Path:
    # Same lock file as swane.utils.templates.get_swane_template: every
    # TemplateFlow download in SWANe is serialised on it. Never take it while
    # already holding it in this process (see swane/utils/wm_prior.py).
    from swane.utils.templates import _SWANE_TEMPLATE_CACHE

    return _SWANE_TEMPLATE_CACHE / ".templateflow_fetch.lock"


def _md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _cached_paths() -> dict:
    folder = _templateflow_home() / ("tpl-" + TEMPLATE)
    return {key: str(folder / name) for key, (name, _q) in ANATOMY_FILES.items()}


def _present(path: str) -> bool:
    # TemplateFlow keeps 0-byte placeholders for files it has not fetched yet.
    return os.path.isfile(path) and os.path.getsize(path) > 0


def anatomy_available() -> bool:
    """True when every file is already in the TemplateFlow cache (no network)."""
    return all(_present(p) for p in _cached_paths().values())


def _mismatch_error(key: str, path: str, got: str) -> RuntimeError:
    return RuntimeError(
        "phantom anatomy file %s has md5 %s, expected %s: a corrupted or partial "
        "download, or an upstream TemplateFlow change. delete %s and retry; if it "
        "persists, re-validate the pre-release sweep on the new file and re-pin "
        "ANATOMY_MD5" % (path, got, ANATOMY_MD5[key], path)
    )


def _mismatched(files: dict) -> list:
    return [k for k, p in files.items() if _md5(p) != ANATOMY_MD5[k]]


def _fetch(key: str) -> str:
    try:
        return _tf_get(ANATOMY_FILES[key][1])
    except Exception as exc:
        raise RuntimeError(
            "could not fetch %s from TemplateFlow (%s): %s"
            % (ANATOMY_FILES[key][0], _templateflow_home(), exc)
        ) from exc


def _verify(files: dict, allow_download: bool) -> None:
    bad = _mismatched(files)
    if bad and allow_download:
        # TemplateFlow streams into the final path, so an interrupted download
        # (or one still running in another process) leaves a non-empty file
        # that counts as present. Under the fetch lock, re-hash (a concurrent
        # fetch may have finished meanwhile), then re-fetch what still differs.
        with FileLock(str(_lock_path())).acquire(timeout=_LOCK_TIMEOUT_SECONDS):
            for key in _mismatched({k: files[k] for k in bad}):
                os.unlink(files[key])
                files[key] = _fetch(key)
        bad = _mismatched(files)
    if bad:
        key = bad[0]
        raise _mismatch_error(key, files[key], _md5(files[key]))


def resolve_anatomy_files(allow_download: bool = True) -> dict:
    """Return ``key -> path`` for the six anatomy files, fetching them if needed."""
    files = _cached_paths()
    missing = [k for k, p in files.items() if not _present(p)]
    if missing and not allow_download:
        raise RuntimeError(
            "phantom anatomy not in the TemplateFlow cache (%s): missing %s"
            % (_templateflow_home(), ", ".join(ANATOMY_FILES[k][0] for k in missing))
        )
    if missing:
        with FileLock(str(_lock_path())).acquire(timeout=_LOCK_TIMEOUT_SECONDS):
            for key in missing:
                if _present(files[key]):
                    continue  # fetched by another process while we waited
                files[key] = _fetch(key)
    _verify(files, allow_download)
    return files


def anatomy_fingerprint(files: dict) -> str:
    """md5 over the file contents, in a fixed key order: the anatomy, not its path."""
    digest = hashlib.md5()
    for key in sorted(files):
        digest.update(key.encode())
        digest.update(_md5(files[key]).encode())
    return digest.hexdigest()
