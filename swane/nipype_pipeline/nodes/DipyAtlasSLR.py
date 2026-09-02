# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Whole-brain Streamline-based Linear Registration (SLR) against the HCP842 atlas.

The SLR is the most expensive part of RecoBundles, so it runs **once** here
(spec section 6): the subject tractogram is aligned to the atlas whole-brain
tractogram, and both the aligned tractogram and the inverse transform are
published for the per-tract bundle recognition in Phase 2.

The 649 MB HCP842 atlas is fetched into a local ``DIPY_HOME`` on first use. Since
SWANe processes subjects in parallel, two workflows finding an empty atlas
directory must not both download it: :func:`ensure_atlas` guards the fetch with a
cross-process file lock, raises a readable :class:`AtlasFetchError` when offline
instead of an opaque traceback, and removes a partial directory left by a failed
attempt before retrying. The whole-brain tractogram is addressed by its explicit
filename (:data:`WHOLE_BRAIN_FILENAME`), never by globbing the bundles directory,
so the misspelled duplicate ``IF0F_R.trk`` shipped in the atlas is never selected.
"""

import importlib
import os
import shutil
from os.path import abspath, basename
from pathlib import Path

import numpy as np
from filelock import FileLock, Timeout
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    Directory,
    isdefined,
)

OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"

# Layout of the fetched atlas, matching dipy's fetcher. The whole-brain
# tractogram is addressed by this explicit name -- never by a glob over the
# sibling ``bundles`` directory, which contains the misspelled duplicate
# ``IF0F_R.trk`` alongside the correct ``IFOF_R.trk``.
ATLAS_SUBDIR = "bundle_atlas_hcp842"
ATLAS_NAME = "Atlas_80_Bundles"
WHOLE_BRAIN_FILENAME = "whole_brain_MNI.trk"

# The lock file lives beside the atlas so every subject sharing a DIPY_HOME
# contends on the same lock.
_LOCK_FILENAME = ".hcp842_fetch.lock"
# A 649 MB download over a slow link can take a while; wait rather than fail.
_LOCK_TIMEOUT_SECONDS = 3600


class AtlasFetchError(RuntimeError):
    """Raised when the HCP842 atlas cannot be made available (e.g. offline)."""


def atlas_wholebrain_path(atlas_dir):
    """Explicit path to the atlas whole-brain tractogram under ``atlas_dir``."""
    return (
        Path(atlas_dir)
        / ATLAS_SUBDIR
        / ATLAS_NAME
        / "whole_brain"
        / WHOLE_BRAIN_FILENAME
    )


def _redirected_fetcher(atlas_dir):
    """Reload dipy's fetcher with ``DIPY_HOME`` pointed at ``atlas_dir``.

    dipy bakes the atlas download folder into the fetcher at import time from the
    module-global ``dipy_home``; reloading after setting ``DIPY_HOME`` rebuilds
    it against ``atlas_dir`` regardless of any earlier import in this process.
    """
    os.environ["DIPY_HOME"] = str(atlas_dir)
    import dipy.data.fetcher as fetcher

    return importlib.reload(fetcher)


def _default_fetch(atlas_dir):
    """Fetch the HCP842 atlas into ``atlas_dir`` via dipy."""
    fetcher = _redirected_fetcher(atlas_dir)
    fetcher.fetch_bundle_atlas_hcp842()


def _default_wholebrain(atlas_dir):
    """Whole-brain path as dipy resolves it (explicit filename, never a glob)."""
    fetcher = _redirected_fetcher(atlas_dir)
    file1, _ = fetcher.get_bundle_atlas_hcp842()
    return Path(file1)


def ensure_atlas(
    atlas_dir,
    *,
    fetch_fn=_default_fetch,
    wholebrain_fn=_default_wholebrain,
    lock_timeout=_LOCK_TIMEOUT_SECONDS,
):
    """Return the whole-brain tractogram path, fetching the atlas if needed.

    The fetch is serialised with a cross-process file lock so concurrent
    subjects trigger exactly one download; a partial atlas directory left by a
    previous failure is removed before (re)fetching; and a fetch failure raises
    :class:`AtlasFetchError` with a readable message. ``fetch_fn`` and
    ``wholebrain_fn`` are injection points for the concurrency/offline tests.
    """
    atlas_dir = Path(atlas_dir)
    atlas_dir.mkdir(parents=True, exist_ok=True)

    wholebrain = Path(wholebrain_fn(str(atlas_dir)))
    if wholebrain.exists():
        return str(wholebrain)

    lock = FileLock(str(atlas_dir / _LOCK_FILENAME))
    try:
        with lock.acquire(timeout=lock_timeout):
            # Re-check under the lock: another subject may have just fetched it.
            wholebrain = Path(wholebrain_fn(str(atlas_dir)))
            if wholebrain.exists():
                return str(wholebrain)

            # Remove any partial atlas tree from an interrupted attempt so the
            # fetch always sees a clean directory.
            partial = atlas_dir / ATLAS_SUBDIR
            if partial.exists():
                shutil.rmtree(partial, ignore_errors=True)

            try:
                fetch_fn(str(atlas_dir))
            except Exception as error:
                if partial.exists():
                    shutil.rmtree(partial, ignore_errors=True)
                raise AtlasFetchError(
                    "Could not download the HCP842 bundle atlas required by the "
                    "dipy tractography engine; the machine appears to be offline. "
                    f"Check the network connection and retry. Underlying error: {error}"
                ) from error

            wholebrain = Path(wholebrain_fn(str(atlas_dir)))
            if not wholebrain.exists():
                raise AtlasFetchError(
                    "The HCP842 atlas fetch completed but the whole-brain "
                    f"tractogram is missing at {wholebrain}."
                )
            return str(wholebrain)
    except Timeout as error:
        raise AtlasFetchError(
            "Timed out waiting for another subject to finish downloading the "
            "HCP842 bundle atlas."
        ) from error


def _run_whole_brain_slr(static, moving, num_threads):
    """Run dipy's whole-brain SLR of ``moving`` (native) onto ``static`` (atlas).

    Returns ``(moved, native2atlas)`` where ``moved`` are the subject streamlines
    in atlas space and ``native2atlas`` is the 4x4 forward transform.
    """
    from dipy.align.streamlinear import whole_brain_slr

    moved, matrix, _, _ = whole_brain_slr(static, moving, num_threads=num_threads)
    return moved, matrix


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyAtlasSLRInputSpec(BaseInterfaceInputSpec):
    tractogram = File(
        exists=True,
        mandatory=True,
        desc="the subject whole-brain tractogram in reference/native space",
    )
    atlas_dir = Directory(
        mandatory=True,
        desc="local DIPY_HOME holding (or receiving) the HCP842 atlas",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the SLR optimisation"
    )
    out_tractogram = File(desc="the atlas-aligned tractogram (.trx)")
    out_atlas2native = File(desc="text file with the 4x4 atlas->native transform")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyAtlasSLROutputSpec(TraitedSpec):
    tractogram_atlas = File(desc="the subject tractogram aligned to the atlas (.trx)")
    atlas2native = File(desc="the 4x4 atlas->native transform (text)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyAtlasSLR(BaseInterface):
    """
    Aligns a subject whole-brain tractogram to the HCP842 atlas with a single
    streamline-based linear registration, publishing the aligned tractogram and
    the inverse (atlas->native) transform for Phase 2 bundle recognition.

    """

    input_spec = DipyAtlasSLRInputSpec
    output_spec = DipyAtlasSLROutputSpec

    def _run_interface(self, runtime):
        from dipy.io.streamline import load_tractogram, save_tractogram
        from dipy.io.stateful_tractogram import StatefulTractogram

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )

        wholebrain = ensure_atlas(self.inputs.atlas_dir)

        out_tractogram = self._gen_outfilename("out_tractogram", "atlas_", ".trx")
        out_atlas2native = self._gen_outfilename(
            "out_atlas2native", "atlas2native_", ".txt"
        )

        previous = {
            var: os.environ.get(var) for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR)
        }
        for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR):
            os.environ[var] = str(num_threads)
        try:
            subject_sft = load_tractogram(
                self.inputs.tractogram, "same", bbox_valid_check=False
            )
            subject_sft.to_rasmm()
            atlas_sft = load_tractogram(wholebrain, "same", bbox_valid_check=False)
            atlas_sft.to_rasmm()

            moved, native2atlas = _run_whole_brain_slr(
                atlas_sft.streamlines, subject_sft.streamlines, num_threads
            )
        finally:
            for var, value in previous.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value

        atlas2native = np.linalg.inv(native2atlas)
        np.savetxt(out_atlas2native, atlas2native)

        # The moved streamlines live in atlas world space; anchor them to the
        # atlas tractogram's spatial reference.
        moved_sft = StatefulTractogram.from_sft(moved, atlas_sft)
        save_tractogram(moved_sft, out_tractogram, bbox_valid_check=False)

        return runtime

    def _gen_outfilename(self, trait_name, prefix, suffix):
        out_file = getattr(self.inputs, trait_name)
        if not isdefined(out_file):
            base = basename(self.inputs.tractogram)
            for ext in (".trx", ".trk", ".tck"):
                if base.endswith(ext):
                    base = base[: -len(ext)]
                    break
            out_file = prefix + base + suffix
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["tractogram_atlas"] = self._gen_outfilename(
            "out_tractogram", "atlas_", ".trx"
        )
        outputs["atlas2native"] = self._gen_outfilename(
            "out_atlas2native", "atlas2native_", ".txt"
        )
        return outputs
