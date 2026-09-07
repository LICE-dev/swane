# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
RecoBundles recognition of a single named atlas bundle in a subject tractogram.

Phase 1 (:class:`~swane.nipype_pipeline.nodes.DipyAtlasSLR.DipyAtlasSLR`) already
aligned the whole subject tractogram to the HCP842 atlas once, so this node
consumes ``tractogram_atlas`` and runs dipy's :class:`RecoBundles` for the one
model bundle named by ``model_bundle_name`` (spec section 6), producing the
recognised streamlines in atlas space as a ``.trx`` file. Bringing the bundle
back to reference space is the bundle workflow's job, not this node's.

The model bundle is addressed by its **explicit filename**
(``<atlas>/bundles/<name>.trk``), never by globbing the ``bundles`` directory:
the atlas ships a misspelled duplicate ``IF0F_R.trk`` (digit zero) alongside the
correct ``IFOF_R.trk``, and a glob could pick the wrong one (spec section 3).

``reduction_thr`` / ``pruning_thr`` / ``model_clust_thr`` are **scientific**
recognition parameters (their defaults chosen later during the AF/CST recovery
work); they are exposed as inputs and never tuned for RAM.

Memory. The peak of RecoBundles is loading and clustering the whole tractogram
once in :class:`RecoBundles`; ``recognize`` itself is cheap (it works on cluster
centroids and a reduced neighbourhood). Two levers bound that peak:

* ``num_threads`` pins the OpenMP/BLAS pool for the local SLR;
* ``chunk_size`` switches to a memmapped **chunk-and-union** path: the tractogram
  is read in chunks of that many streamlines (never materialised whole),
  recognised chunk by chunk, and the recognised streamlines are unioned. This is
  only *scientifically* valid with the local SLR off -- each chunk would otherwise
  compute a different local SLR and the union would not equal the whole-tractogram
  result -- so setting ``chunk_size`` **implies** the local SLR is disabled and
  the ``slr`` input is ignored. The whole-brain SLR done once in Phase 1 already
  provides global alignment; the per-recognition local SLR (``slr=True``, the
  single-pass default) is a finer, bundle-specific refinement, so chunking trades
  that refinement for RAM.

Carries a **static** conservative ``_mem_gb`` placeholder; the tunable estimator
that replaces it is a separate task.
"""

import os
from os.path import abspath, basename

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    Directory,
    isdefined,
)

# Reuse the atlas layout constants so the bundles path stays a single source of
# truth with the whole-brain SLR node.
from swane.nipype_pipeline.nodes.DipyAtlasSLR import ATLAS_SUBDIR, ATLAS_NAME

OMP_THREADS_VAR = "OMP_NUM_THREADS"
OPENBLAS_THREADS_VAR = "OPENBLAS_NUM_THREADS"

# The atlas ``bundles`` directory, sibling of ``whole_brain``. Bundles are
# addressed as ``<atlas>/bundle_atlas_hcp842/Atlas_80_Bundles/bundles/<name>.trk``
# by explicit name -- never by a glob that could catch the misspelled duplicate
# ``IF0F_R.trk``.
BUNDLES_SUBDIR = "bundles"
BUNDLE_EXTENSION = ".trk"

# Fixed RNG seed so recognition is reproducible run-to-run. Kept a module
# constant (not an input) so the workflow graph and golden snapshots are
# unaffected, mirroring the tracking length constants.
RECOBUNDLES_RNG_SEED = 1234

# dipy RecoBundles defaults kept as module constants (not scientific levers).
CLUST_THR = 15.0
NB_PTS = 20

# Conservative static placeholder (~ the Phase-1bis figure) until the tunable
# RAM estimator replaces it.
STATIC_MEM_GB = 8.0


def bundle_path(atlas_dir, model_bundle_name):
    """Explicit path to ``model_bundle_name`` inside ``atlas_dir``'s bundles.

    ``model_bundle_name`` is a bare basename (e.g. ``"IFOF_R"``); the ``.trk``
    extension is appended here. No globbing: the returned path names exactly the
    requested file, so the misspelled ``IF0F_R.trk`` is only ever reached by
    asking for ``"IF0F_R"`` explicitly.
    """
    name = str(model_bundle_name)
    if name.endswith(BUNDLE_EXTENSION):
        name = name[: -len(BUNDLE_EXTENSION)]
    return os.path.join(
        str(atlas_dir),
        ATLAS_SUBDIR,
        ATLAS_NAME,
        BUNDLES_SUBDIR,
        name + BUNDLE_EXTENSION,
    )


def _recognize(
    streamlines,
    model_bundle,
    *,
    model_clust_thr,
    reduction_thr,
    pruning_thr,
    slr,
    num_threads,
):
    """Run one dipy RecoBundles recognition and return the recognised streamlines.

    A thin wrapper over :class:`dipy.segment.bundles.RecoBundles` (seeded for
    reproducibility) so the thread-pinning test can spy the OpenMP environment at
    the exact call site.
    """
    from dipy.segment.bundles import RecoBundles

    rb = RecoBundles(
        streamlines,
        clust_thr=CLUST_THR,
        nb_pts=NB_PTS,
        rng=np.random.default_rng(RECOBUNDLES_RNG_SEED),
        verbose=False,
    )
    recognized, _ = rb.recognize(
        model_bundle,
        model_clust_thr,
        reduction_thr=reduction_thr,
        pruning_thr=pruning_thr,
        slr=slr,
        num_threads=num_threads,
    )
    return recognized


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyRecoBundlesInputSpec(BaseInterfaceInputSpec):
    tractogram_atlas = File(
        exists=True,
        mandatory=True,
        desc="the subject whole-brain tractogram aligned to the atlas (.trx)",
    )
    atlas_dir = Directory(
        mandatory=True,
        desc="local DIPY_HOME holding the HCP842 atlas",
    )
    model_bundle_name = traits.Str(
        mandatory=True,
        desc="explicit atlas bundle basename without extension, e.g. 'IFOF_R'",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the recognition/local SLR"
    )
    # Scientific recognition parameters -- chosen during the AF/CST recovery work,
    # never tuned for RAM. Defaults are dipy's documented defaults so the node
    # runs standalone.
    reduction_thr = traits.Float(
        10.0,
        usedefault=True,
        desc="scientific: search-space reduction distance (mm)",
    )
    pruning_thr = traits.Float(
        5.0,
        usedefault=True,
        desc="scientific: pruning distance (mm)",
    )
    model_clust_thr = traits.Float(
        2.5,
        usedefault=True,
        desc="scientific: model-bundle clustering MDF threshold (mm)",
    )
    slr = traits.Bool(
        True,
        usedefault=True,
        desc="run RecoBundles' local (per-bundle) SLR in single-pass mode; "
        "ignored (forced off) when chunk_size is set, since a union of per-chunk "
        "SLRs is invalid",
    )
    chunk_size = traits.Int(
        nohash=True,
        desc="if set (>0 and < number of streamlines), recognise the tractogram "
        "in memmapped chunks of this many streamlines and union the results (a "
        "RAM lever); this disables the local SLR automatically",
    )
    out_bundle = File(desc="the recognised bundle output (.trx)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyRecoBundlesOutputSpec(TraitedSpec):
    recognized_bundle = File(
        desc="the recognised bundle in atlas space (.trx); empty-but-valid when "
        "the model shape is absent from the tractogram"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyRecoBundles(BaseInterface):
    """
    Recognises a single named HCP842 atlas bundle inside the atlas-aligned
    subject tractogram with dipy's RecoBundles, writing the recognised
    streamlines (atlas space) to a ``.trx`` file. The model bundle is addressed
    by explicit filename; an optional memmapped chunk-and-union path bounds the
    memory of a very large tractogram.

    """

    input_spec = DipyRecoBundlesInputSpec
    output_spec = DipyRecoBundlesOutputSpec

    # Static conservative placeholder; replaced by the tunable RAM estimator in a
    # later task.
    _mem_gb = STATIC_MEM_GB

    def _run_interface(self, runtime):
        from dipy.io.streamline import load_tractogram, save_tractogram
        from dipy.io.stateful_tractogram import StatefulTractogram

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        chunk_size = (
            int(self.inputs.chunk_size) if isdefined(self.inputs.chunk_size) else 0
        )

        model_file = bundle_path(self.inputs.atlas_dir, self.inputs.model_bundle_name)
        if not os.path.exists(model_file):
            raise FileNotFoundError(
                f"atlas model bundle '{basename(model_file)}' not found at "
                f"{model_file}"
            )

        out_bundle = self._gen_outfilename()

        # Anchor the recognised output to the atlas model's spatial reference; the
        # recognised streamlines live in the atlas (model) world space.
        model_sft = load_tractogram(model_file, "same", bbox_valid_check=False)
        model_sft.to_rasmm()
        model_bundle = model_sft.streamlines

        previous = {
            var: os.environ.get(var) for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR)
        }
        for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR):
            os.environ[var] = str(num_threads)
        try:
            if chunk_size > 0:
                recognized = self._recognize_in_chunks(
                    model_bundle, chunk_size, num_threads
                )
            else:
                recognized = self._recognize_single_pass(
                    load_tractogram, model_bundle, num_threads
                )
        finally:
            for var, value in previous.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value

        recognized_sft = StatefulTractogram.from_sft(recognized, model_sft)
        save_tractogram(recognized_sft, out_bundle, bbox_valid_check=False)

        return runtime

    def _recognize_single_pass(self, load_tractogram, model_bundle, num_threads):
        """Recognise on the whole tractogram loaded into memory (exact path)."""
        subject_sft = load_tractogram(
            self.inputs.tractogram_atlas, "same", bbox_valid_check=False
        )
        subject_sft.to_rasmm()
        return _recognize(
            subject_sft.streamlines,
            model_bundle,
            model_clust_thr=float(self.inputs.model_clust_thr),
            reduction_thr=float(self.inputs.reduction_thr),
            pruning_thr=float(self.inputs.pruning_thr),
            slr=bool(self.inputs.slr),
            num_threads=num_threads,
        )

    def _recognize_in_chunks(self, model_bundle, chunk_size, num_threads):
        """Recognise chunk by chunk over a memmapped ``.trx`` and union results.

        The tractogram is never materialised whole: ``TrxFile.select`` points at
        the same memmaps, and only the current chunk's streamlines are pulled
        into memory (``copy_safe``) for recognition. Recognition runs with
        ``slr=False`` (enforced upstream), so unioning the per-chunk recognitions
        approximates the whole-tractogram result within clustering tolerance.
        """
        from trx.trx_file_memmap import load as trx_load

        model_clust_thr = float(self.inputs.model_clust_thr)
        reduction_thr = float(self.inputs.reduction_thr)
        pruning_thr = float(self.inputs.pruning_thr)

        union = []
        trx = trx_load(self.inputs.tractogram_atlas)
        try:
            n = len(trx)
            for start in range(0, n, chunk_size):
                indices = np.arange(start, min(start + chunk_size, n))
                sub = trx.select(indices, copy_safe=True)
                try:
                    sub_sft = sub.to_sft()
                    sub_sft.to_rasmm()
                    recognized = _recognize(
                        sub_sft.streamlines,
                        model_bundle,
                        model_clust_thr=model_clust_thr,
                        reduction_thr=reduction_thr,
                        pruning_thr=pruning_thr,
                        slr=False,
                        num_threads=num_threads,
                    )
                    union.extend(list(recognized))
                finally:
                    sub.close()
        finally:
            trx.close()

        from dipy.tracking.streamline import Streamlines

        return Streamlines(union)

    def _gen_outfilename(self):
        out_file = self.inputs.out_bundle
        if not isdefined(out_file):
            base = basename(self.inputs.tractogram_atlas)
            for ext in (".trx", ".trk", ".tck"):
                if base.endswith(ext):
                    base = base[: -len(ext)]
                    break
            name = str(self.inputs.model_bundle_name)
            out_file = f"recognized_{name}_{base}.trx"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["recognized_bundle"] = self._gen_outfilename()
        return outputs
