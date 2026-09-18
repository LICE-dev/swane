"""Tests for the file-locked HCP842 atlas fetch in
:mod:`swane.nipype_pipeline.nodes.DipyAtlasSLR`.

SWANe processes subjects in parallel, so two workflows that both find an empty
``DIPY_HOME`` must not each download the 649 MB atlas (spec section 8). The
requirements verified here:

* two concurrent fetches against one empty ``DIPY_HOME`` trigger exactly one
  download and leave no corruption;
* an offline fetch raises a readable error rather than an opaque traceback;
* a partial atlas directory left by a failed attempt is removed on retry.

The concurrency test uses real subprocesses (as nipype's ``MultiProc`` does),
with a lightweight fetch injected in place of the real 649 MB download so the
lock -- not the network -- is what is exercised.
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor

import pytest

from swane.nipype_pipeline.nodes.DipyAtlasSLR import (
    ensure_atlas,
    AtlasFetchError,
    ATLAS_SUBDIR,
)


# --------------------------------------------------------------------------- #
# Module-level helpers so ProcessPoolExecutor (spawn-safe) can pickle them.
# --------------------------------------------------------------------------- #
def _wholebrain_for(atlas_dir):
    """Deterministic whole-brain path under a test atlas dir (no dipy needed)."""
    return os.path.join(
        atlas_dir,
        ATLAS_SUBDIR,
        "Atlas_80_Bundles",
        "whole_brain",
        "whole_brain_MNI.trk",
    )


def _slow_fake_fetch(atlas_dir):
    """Stand in for the real fetch: record the call, then create the atlas.

    Each invocation appends a line to ``<atlas_dir>/fetch.log`` (append is
    atomic for a short write) and, after a small delay to widen the race, writes
    the whole-brain file so a subsequent existence check succeeds.
    """
    with open(os.path.join(atlas_dir, "fetch.log"), "a") as handle:
        handle.write(f"{os.getpid()}\n")
    time.sleep(0.5)
    wb = _wholebrain_for(atlas_dir)
    os.makedirs(os.path.dirname(wb), exist_ok=True)
    with open(wb, "wb") as handle:
        handle.write(b"synthetic whole brain tractogram")


def _worker(atlas_dir):
    ensure_atlas(atlas_dir, fetch_fn=_slow_fake_fetch, wholebrain_fn=_wholebrain_for)
    return True


# --------------------------------------------------------------------------- #
# Concurrency: exactly one download.
# --------------------------------------------------------------------------- #
class TestConcurrentFetch:
    def test_two_processes_download_once(self, tmp_path):
        atlas_dir = str(tmp_path / "dipy_home")
        os.makedirs(atlas_dir, exist_ok=True)

        with ProcessPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(_worker, [atlas_dir, atlas_dir]))

        assert results == [True, True]
        with open(os.path.join(atlas_dir, "fetch.log")) as handle:
            fetches = [line for line in handle if line.strip()]
        assert len(fetches) == 1  # exactly one process fetched
        assert os.path.exists(_wholebrain_for(atlas_dir))

    def test_present_atlas_skips_fetch(self, tmp_path):
        atlas_dir = str(tmp_path / "dipy_home")
        wb = _wholebrain_for(atlas_dir)
        os.makedirs(os.path.dirname(wb), exist_ok=True)
        open(wb, "wb").write(b"already here")

        def _must_not_fetch(_atlas_dir):
            raise AssertionError("fetch must not run when the atlas is present")

        result = ensure_atlas(
            atlas_dir, fetch_fn=_must_not_fetch, wholebrain_fn=_wholebrain_for
        )
        assert result == wb


# --------------------------------------------------------------------------- #
# Offline: readable error, partial directory cleaned.
# --------------------------------------------------------------------------- #
class TestOfflineFailure:
    def test_offline_raises_readable_error_and_cleans_partial(self, tmp_path):
        atlas_dir = str(tmp_path / "dipy_home")
        os.makedirs(atlas_dir, exist_ok=True)
        partial = os.path.join(atlas_dir, ATLAS_SUBDIR)

        def _offline_fetch(_atlas_dir):
            # simulate a fetch that writes a partial tree, then fails offline
            os.makedirs(partial, exist_ok=True)
            open(os.path.join(partial, "half.zip"), "wb").write(b"incomplete")
            raise ConnectionError("Temporary failure in name resolution")

        with pytest.raises(AtlasFetchError) as excinfo:
            ensure_atlas(
                atlas_dir, fetch_fn=_offline_fetch, wholebrain_fn=_wholebrain_for
            )

        message = str(excinfo.value).lower()
        assert "atlas" in message and "offline" in message
        # the partial directory left by the failed attempt is gone
        assert not os.path.exists(partial)


# --------------------------------------------------------------------------- #
# Retry: a stale partial directory is removed before re-fetching.
# --------------------------------------------------------------------------- #
class TestRetryCleansPartial:
    def test_stale_partial_removed_then_fetched(self, tmp_path):
        atlas_dir = str(tmp_path / "dipy_home")
        stale = os.path.join(atlas_dir, ATLAS_SUBDIR, "leftover")
        os.makedirs(stale, exist_ok=True)
        open(os.path.join(stale, "junk.tmp"), "wb").write(b"stale")

        calls = {"n": 0}

        def _good_fetch(a_dir):
            calls["n"] += 1
            # a real fetch would only ever see a clean directory
            assert not os.path.exists(stale), "stale partial not cleaned before fetch"
            _slow_fake_fetch(a_dir)

        result = ensure_atlas(
            atlas_dir, fetch_fn=_good_fetch, wholebrain_fn=_wholebrain_for
        )
        assert calls["n"] == 1
        assert result == _wholebrain_for(atlas_dir)
        assert os.path.exists(result)
