# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Fornix lateralisation: the atlas's ``fx`` special case (spec section 3).

Every other bilateral tract the HCP842 atlas ships already carries separate
``<NAME>_L``/``<NAME>_R`` model files, so :class:`~swane.nipype_pipeline.nodes.
DipyRecoBundles.DipyRecoBundles` recognises each side with its own call. The
fornix is the one exception: the atlas ships both sides combined in a single
``F_L_R.trk``.

This module lateralises that one model bundle -- **once, on the atlas's own
file**, not per subject -- by the sign of x, producing ``F_L.trk``/``F_R.trk``
cached beside it in the atlas's ``bundles`` directory. Every subject's fornix
recognition then reuses those two files exactly like any other named atlas
bundle: ``DipyRecoBundles`` needs no fornix-specific code at all, and the
lateralisation cost (a plain array split, not a re-registration) is paid at
most once per shared atlas directory, never once per subject.

**Space.** The split runs directly on ``F_L_R.trk`` in the atlas's own RASMM
world space -- the same space every other atlas model bundle already lives in
and where the atlas's left/right convention is documented and verified (spec
section 3: ``AST_L`` spans x[-56,-8], i.e. negative x is left). No subject
tractogram, transform or diffusion-space data is ever involved: the fornix
split is purely a one-time preparation of the shared atlas resource, so there
is no "wrong subject space" for it to run in by construction. ``load_tractogram``
converts to RASMM on load (mirroring the explicit ``to_rasmm()`` calls already
used by :class:`DipyRecoBundles.DipyRecoBundles`/``DipyAtlasSLR``), so the split
reads true anatomical world coordinates rather than a file's raw voxel storage
order.

**Anatomical validity guard.** A sign-of-x split is only meaningful for a
genuinely paired (bilateral) structure shipped as one combined file -- the
fornix is exactly that. It would be meaningless for a commissure (e.g. ``AC``,
the anterior commissure): a commissure is a single midline structure with no
left/right identity, so :func:`split_by_sign_x` refuses any bundle name other
than the fornix's (:data:`SPLITTABLE_BUNDLE_NAMES`).

Concurrency mirrors :func:`~swane.nipype_pipeline.nodes.DipyAtlasSLR.ensure_atlas`:
SWANe processes subjects in parallel, and two subjects finding ``F_L.trk``
missing must not race to (re)write it. :func:`ensure_fornix_lateralized` is
guarded by the same cross-process file-lock pattern, with a fast lock-free path
once both files exist.
"""

import os
import tempfile
from pathlib import Path

import numpy as np
from filelock import FileLock, Timeout
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    Directory,
)

# Reuse the atlas bundle-path helper so the fornix files sit in exactly the
# same ``bundles`` directory as every other named atlas bundle.
from swane.nipype_pipeline.nodes.DipyRecoBundles import bundle_path

# The atlas's combined fornix model and the lateralised names this module
# produces for it. Only "F_L_R" may ever be split (see SPLITTABLE_BUNDLE_NAMES
# below) -- these two names are not a general convention, just this one
# bundle's lateralised siblings.
FORNIX_COMBINED_NAME = "F_L_R"
FORNIX_LEFT_NAME = "F_L"
FORNIX_RIGHT_NAME = "F_R"

# Bundle names for which a sign-of-x split is anatomically meaningful: a
# paired structure the atlas ships as one side-combined file. Currently only
# the fornix. Never a commissure (e.g. "AC") -- a commissure has no left/right
# identity to split.
SPLITTABLE_BUNDLE_NAMES = frozenset({FORNIX_COMBINED_NAME})

# The lock file lives beside the atlas, mirroring DipyAtlasSLR's convention,
# so every subject sharing a DIPY_HOME contends on the same lock.
_LOCK_FILENAME = ".fornix_split.lock"
# Splitting an already-loaded model bundle is fast (no registration, no
# clustering); a modest timeout is enough to wait out a concurrent writer.
_LOCK_TIMEOUT_SECONDS = 300


class FornixSplitRefusedError(ValueError):
    """Raised when a sign-of-x split is requested for a non-paired bundle."""


def split_by_sign_x(streamlines, model_bundle_name):
    """Partition ``streamlines`` (world/RASMM space) by the sign of each
    streamline's mean x coordinate.

    Returns ``(lh_idx, rh_idx)``: integer index arrays into ``streamlines``,
    left (x<0) and right (x>=0) respectively, covering every streamline
    exactly once. Refuses (:class:`FornixSplitRefusedError`) any
    ``model_bundle_name`` outside :data:`SPLITTABLE_BUNDLE_NAMES` -- this split
    is anatomically valid only for a paired structure shipped as one combined
    file, never for a commissure or any other single-midline bundle.
    """
    if model_bundle_name not in SPLITTABLE_BUNDLE_NAMES:
        raise FornixSplitRefusedError(
            f"sign-of-x split refused for '{model_bundle_name}': anatomically "
            "valid only for a paired structure shipped as one side-combined "
            f"atlas file ({sorted(SPLITTABLE_BUNDLE_NAMES)}), never for a "
            "commissure or any other single-midline bundle."
        )

    x_mean = np.array([np.mean(np.asarray(sl)[:, 0]) for sl in streamlines])
    lh_idx = np.where(x_mean < 0)[0]
    rh_idx = np.where(x_mean >= 0)[0]
    return lh_idx, rh_idx


def _split_and_save(combined_path, out_lh, out_rh):
    """Load ``combined_path``, split it, and atomically write ``out_lh``/``out_rh``.

    Writes to temporary files first and renames them into place last, so no
    caller ever observes a partially written ``F_L.trk``/``F_R.trk``.
    """
    from dipy.io.streamline import load_tractogram, save_tractogram

    sft = load_tractogram(combined_path, "same", bbox_valid_check=False)
    sft.to_rasmm()
    lh_idx, rh_idx = split_by_sign_x(sft.streamlines, FORNIX_COMBINED_NAME)

    # Indexing a StatefulTractogram with an index array returns a new
    # StatefulTractogram sharing the same spatial reference/space.
    sft_lh = sft[lh_idx]
    sft_rh = sft[rh_idx]

    out_dir = os.path.dirname(out_lh)
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out_dir) as tmp_dir:
        tmp_lh = os.path.join(tmp_dir, os.path.basename(out_lh))
        tmp_rh = os.path.join(tmp_dir, os.path.basename(out_rh))
        save_tractogram(sft_lh, tmp_lh, bbox_valid_check=False)
        save_tractogram(sft_rh, tmp_rh, bbox_valid_check=False)
        os.replace(tmp_lh, out_lh)
        os.replace(tmp_rh, out_rh)


def ensure_fornix_lateralized(atlas_dir, *, lock_timeout=_LOCK_TIMEOUT_SECONDS):
    """Return ``(path_lh, path_rh)``, splitting the atlas's ``F_L_R.trk`` the
    first time they are needed.

    Fast path: if both lateralised files already exist, return them without
    taking the lock. Otherwise the split is serialised with a cross-process
    file lock (mirroring :func:`~swane.nipype_pipeline.nodes.DipyAtlasSLR.
    ensure_atlas`) so concurrent subjects sharing the same atlas directory
    trigger exactly one split; the lock is re-checked for the same
    already-done condition before splitting, in case another subject just
    finished while this one waited.

    Raises :class:`FileNotFoundError` if the atlas's own ``F_L_R.trk`` is
    missing -- that is a broken/incomplete atlas, not something this function
    can repair.
    """
    path_lh = bundle_path(atlas_dir, FORNIX_LEFT_NAME)
    path_rh = bundle_path(atlas_dir, FORNIX_RIGHT_NAME)
    if os.path.exists(path_lh) and os.path.exists(path_rh):
        return path_lh, path_rh

    lock = FileLock(str(Path(atlas_dir) / _LOCK_FILENAME))
    try:
        with lock.acquire(timeout=lock_timeout):
            if os.path.exists(path_lh) and os.path.exists(path_rh):
                return path_lh, path_rh

            combined_path = bundle_path(atlas_dir, FORNIX_COMBINED_NAME)
            if not os.path.exists(combined_path):
                raise FileNotFoundError(
                    f"atlas fornix model bundle '{FORNIX_COMBINED_NAME}.trk' "
                    f"not found at {combined_path}; cannot lateralise it."
                )

            _split_and_save(combined_path, path_lh, path_rh)
            return path_lh, path_rh
    except Timeout as error:
        raise FileNotFoundError(
            "Timed out waiting for another subject to finish lateralising the "
            "fornix atlas bundle."
        ) from error


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyFornixSplitInputSpec(BaseInterfaceInputSpec):
    atlas_dir = Directory(
        exists=True,
        mandatory=True,
        desc="local DIPY_HOME holding the HCP842 atlas",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyFornixSplitOutputSpec(TraitedSpec):
    atlas_dir = Directory(
        desc="the same atlas_dir, passed through once F_L.trk/F_R.trk exist "
        "-- a bundle workflow depends on this output to order two ordinary "
        "DipyRecoBundles recognitions (model_bundle_name='F_L'/'F_R') after it"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyFornixSplit(BaseInterface):
    """
    Ensures the atlas's lateralised fornix bundles (``F_L.trk``/``F_R.trk``)
    exist, splitting the shipped ``F_L_R.trk`` by sign of x the first time any
    subject needs it (see module docstring). Downstream, the fornix is
    recognised exactly like any other bilateral tract: two ordinary
    ``DipyRecoBundles`` nodes with ``model_bundle_name='F_L'``/``'F_R'``,
    depending on this node's ``atlas_dir`` output to run after it.

    """

    input_spec = DipyFornixSplitInputSpec
    output_spec = DipyFornixSplitOutputSpec

    def _run_interface(self, runtime):
        ensure_fornix_lateralized(self.inputs.atlas_dir)
        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["atlas_dir"] = self.inputs.atlas_dir
        return outputs
