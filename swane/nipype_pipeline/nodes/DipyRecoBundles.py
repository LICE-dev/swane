# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
RecoBundles bundle recognition, split into a shared **build** and a per-tract
**recognise** (user design 2026-09-07).

The cost of RecoBundles is entirely in :class:`RecoBundles.__init__`: it runs a
QuickBundlesX clustering of the whole (sub-)tractogram. ``recognize`` itself is
cheap -- it works on the cached cluster centroids and a reduced neighbourhood.
So the expensive clustering is built **once** per (sub-)tractogram
(:class:`DipyRecoBundlesBuild`) and every tract merely reloads it and recognises
its own model bundle (:class:`DipyRecoBundlesRecognize`), giving per-tract
completion reports without repeating the clustering.

The model bundle is addressed by its **explicit filename**
(``<atlas>/bundles/<name>.trk``), never by globbing the ``bundles`` directory:
the atlas ships a misspelled duplicate ``IF0F_R.trk`` (digit zero) alongside the
correct ``IFOF_R.trk``, and a glob could pick the wrong one (spec section 3).

``reduction_thr`` / ``pruning_thr`` / ``model_clust_thr`` are **scientific**
recognition parameters (their defaults chosen later during the AF/CST recovery
work); they are exposed as inputs and never tuned for RAM.

Lightweight build -> recognise handoff
--------------------------------------
The build and recognise run in different nodes/processes, so the built object
must be handed over on disk. The naive route -- pickling the whole
:class:`RecoBundles` -- would re-serialise the entire clustered tractogram
(``self.streamlines``), duplicating on disk (and re-materialising in RAM) the
streamlines that already live in the chunk ``.trx`` the build read. Instead the
build pickles only what ``recognize`` cannot recompute cheaply: the QBx
``cluster_map`` (centroids + per-cluster indices) and the **post-clustering RNG
state** (see below). The recognise node reloads the same ``.trx`` streamlines
and reconstructs ``RecoBundles(streamlines, cluster_map=...)``, which skips the
clustering entirely. Measured on a ~0.5 MB tractogram the pickle drops from
~530 KB (whole object) to ~18 KB, and the streamlines are stored once, not
twice -- the disk/RAM minimisation the user asked for.

**Why the RNG state is carried.** A single in-process build advances its RNG
during clustering, and ``recognize`` (specifically the local SLR and the pruning
QBx) consumes the RNG from that advanced state. Reconstructing with an injected
``cluster_map`` does *not* re-run the clustering, so a freshly seeded RNG would
sit at the pre-clustering state and ``recognize`` would diverge. Pickling and
restoring the RNG the build ended with makes a reloaded recognition **bit-for-bit
identical** to an in-process one.

Note this injects the *genuine* ``cluster_map`` the build computed, which is not
the same as injecting a home-made subsample into a fresh build (that would defeat
RecoBundles' internal subsampling); the build itself is always a plain
``RecoBundles(streamlines)`` with no injected clustering.

RAM is reserved at scheduling time by
:class:`~swane.nipype_pipeline.nodes.ram_estimators.RecoBundlesRamEstimator`
(linear in the chunk's point count); the static ``_mem_gb`` is only the
negotiation-failed fail-safe.
"""

import os
import pickle
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

# Recognition parameters, per tract.
#
# ``refine`` is dipy's auto-calibration pass (Chandio BQ, Risacher SL, Pestilli F,
# et al. Bundle analytics, a computational framework for investigating the shapes
# and profiles of brain pathways across populations. Scientific Reports.
# 2020;10:17149): a second pass that rebuilds its search space from the bundle
# just recognised in this subject instead of the population-average atlas model.
#
# Overrides are keyed by the atlas bundle base name, WITHOUT the side suffix, so
# a tract's left and right are always recognised with identical parameters: the
# two are the same anatomical structure, and comparing hemispheres is a normal
# use of the result, which side-dependent parameters would bias by construction.
#
# Applied unchanged for any n_chunks: the per-bundle local SLR and the refine
# pass run on every chunk, and the bundle is written from the streamline indices
# they select, so the per-chunk partials concatenate without further correction.
RECOGNITION_DEFAULTS = {
    "model_clust_thr": 2.5,
    "reduction_thr": 15.0,
    "pruning_thr": 5.0,
    "refine": True,
    "r_reduction_thr": 12.0,
    "r_pruning_thr": 4.0,
}

RECOGNITION_OVERRIDES = {
    "OR": {"r_reduction_thr": 14.0, "r_pruning_thr": 6.0},
    "F": {"r_reduction_thr": 14.0, "r_pruning_thr": 6.0},
    "CST": {"reduction_thr": 12.0},
}

# dipy's own workflow refines with an affine local SLR and explicit bounds rather
# than the bare default; these values assume that, so it is reproduced here.
REFINE_SLR_X0 = np.array([0, 0, 0, 0, 0, 0, 1.0, 1.0, 1.0, 0, 0, 0])
REFINE_SLR_BOUNDS = [
    (-30, 30),
    (-30, 30),
    (-30, 30),
    (-45, 45),
    (-45, 45),
    (-45, 45),
    (0.8, 1.2),
    (0.8, 1.2),
    (0.8, 1.2),
    (-10, 10),
    (-10, 10),
    (-10, 10),
]

# dipy's refine clusters the first-pass bundle, which is not meaningful for a
# single streamline; below this the pass is skipped and the first pass stands.
MIN_STREAMLINES_FOR_REFINE = 2

# The side suffixes an atlas bundle name may carry (``AF_L`` -> tract ``AF``).
_SIDE_SUFFIXES = ("_L", "_R")


def tract_of(model_bundle_name):
    """The tract key of an atlas bundle name, i.e. its name without the side."""
    name = str(model_bundle_name)
    for suffix in _SIDE_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def recognition_params(model_bundle_name):
    """The recognition parameters for one atlas bundle.

    A fresh dict of :data:`RECOGNITION_DEFAULTS` with any
    :data:`RECOGNITION_OVERRIDES` entry for the bundle's *tract* applied, so
    callers may mutate it without the module table drifting. Keying on the tract
    (not the bundle) is what keeps the two sides identical.
    """
    params = dict(RECOGNITION_DEFAULTS)
    params.update(RECOGNITION_OVERRIDES.get(tract_of(model_bundle_name), {}))
    return params


# Conservative static reservation, used only as the build node's
# negotiation-failed fail-safe (RecoBundlesRamEstimator reserves from the chunk's
# point count at scheduling time).
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


def _pin_threads(num_threads):
    """Set OMP/OpenBLAS thread vars, returning their previous values to restore.

    numpy here is linked against scipy-openblas, which otherwise multithreads
    large decompositions on its own -- invisible to nipype's resource
    accounting. Every dipy node pins these to the count it declares (spec
    section 10).
    """
    previous = {
        var: os.environ.get(var) for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR)
    }
    for var in (OMP_THREADS_VAR, OPENBLAS_THREADS_VAR):
        os.environ[var] = str(num_threads)
    return previous


def _restore_threads(previous):
    """Restore the thread env vars saved by :func:`_pin_threads`."""
    for var, value in previous.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


def _build_recobundles(streamlines):
    """Build ``RecoBundles(streamlines)`` with the module clustering constants.

    A plain build -- no injected ``cluster_map`` -- so RecoBundles' internal
    QuickBundlesX subsampling is used as designed. Seeded for reproducibility.
    """
    from dipy.segment.bundles import RecoBundles

    return RecoBundles(
        streamlines,
        clust_thr=CLUST_THR,
        nb_pts=NB_PTS,
        rng=np.random.default_rng(RECOBUNDLES_RNG_SEED),
        verbose=False,
    )


def dump_build(rb, path):
    """Pickle only the reusable part of a built :class:`RecoBundles` to ``path``.

    Stores the QBx ``cluster_map`` (with its ``refdata`` streamlines *stripped*,
    so the streamlines are not dragged into the pickle) and the post-clustering
    RNG state. The streamlines themselves stay in the input ``.trx`` that
    :class:`DipyRecoBundlesRecognize` reloads. See the module docstring.
    """
    cluster_map = rb.cluster_map
    saved_refdata = cluster_map.refdata
    cluster_map.refdata = None
    try:
        with open(path, "wb") as fh:
            pickle.dump(
                {"cluster_map": cluster_map, "rng": rb.rng},
                fh,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
    finally:
        # Leave the in-memory object untouched for any later use in-process.
        cluster_map.refdata = saved_refdata


def load_build(streamlines, path):
    """Reconstruct a built :class:`RecoBundles` from ``streamlines`` + ``path``.

    Injects the pickled ``cluster_map`` so the expensive clustering is skipped,
    and restores the pickled post-clustering RNG state so a subsequent
    ``recognize`` reproduces an in-process build bit-for-bit.
    """
    from dipy.segment.bundles import RecoBundles

    with open(path, "rb") as fh:
        stored = pickle.load(fh)

    rb = RecoBundles(
        streamlines,
        cluster_map=stored["cluster_map"],
        clust_thr=CLUST_THR,
        nb_pts=NB_PTS,
        rng=stored["rng"],
        verbose=False,
    )
    # ``__init__`` already sets ``self.rng`` to the injected generator, but make
    # the contract explicit: recognition resumes from the build's RNG state.
    rb.rng = stored["rng"]
    return rb


def _run_recognize(
    rb,
    model_bundle,
    *,
    model_clust_thr,
    reduction_thr,
    pruning_thr,
    slr,
    num_threads,
):
    """Run one ``RecoBundles.recognize``.

    Returns the recognised streamlines together with their indices in the input
    tractogram. A thin wrapper over
    :meth:`dipy.segment.bundles.RecoBundles.recognize` so the thread-pinning test
    can spy the OpenMP environment at the exact call site.
    """
    recognized, labels = rb.recognize(
        model_bundle,
        model_clust_thr,
        reduction_thr=reduction_thr,
        pruning_thr=pruning_thr,
        slr=slr,
        num_threads=num_threads,
    )
    return recognized, np.asarray(labels, dtype=int)


def _run_refine(
    rb,
    model_bundle,
    recognized,
    *,
    model_clust_thr,
    r_reduction_thr,
    r_pruning_thr,
):
    """Run dipy's auto-calibration pass over a first-pass recognition.

    Returns the refined streamlines together with their indices in the input
    tractogram.

    ``refine`` builds its search space from ``recognized`` -- the bundle found in
    *this* subject -- rather than from the population-average atlas model, which
    is what makes it "auto-calibrated" (Chandio 2020). A thin wrapper so the
    spying test can observe the exact call site, mirroring
    :func:`_run_recognize`.
    """
    refined, labels = rb.refine(
        model_bundle,
        recognized,
        model_clust_thr,
        reduction_thr=r_reduction_thr,
        pruning_thr=r_pruning_thr,
        slr=True,
        slr_x0=REFINE_SLR_X0,
        slr_bounds=REFINE_SLR_BOUNDS,
    )
    return refined, np.asarray(labels, dtype=int)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyRecoBundlesBuildInputSpec(BaseInterfaceInputSpec):
    tractogram_chunk = File(
        exists=True,
        mandatory=True,
        desc="one (sub-)tractogram in atlas space (.trx) to build RecoBundles on",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the QuickBundlesX clustering"
    )
    out_pickle = File(desc="the lightweight built-RecoBundles pickle output")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyRecoBundlesBuildOutputSpec(TraitedSpec):
    recobundles_pickle = File(
        desc="lightweight pickle of the QBx cluster_map + RNG state; the "
        "streamlines are NOT stored here (they stay in tractogram_chunk)"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyRecoBundlesBuild(BaseInterface):
    """
    Builds dipy's :class:`RecoBundles` on one atlas-space (sub-)tractogram --
    the expensive whole-tractogram QuickBundlesX clustering -- and saves it as a
    **lightweight** pickle (cluster map + RNG state only, never the streamlines)
    for one or more :class:`DipyRecoBundlesRecognize` nodes to reload. Runs once
    per (sub-)tractogram and is shared across every tract.

    """

    input_spec = DipyRecoBundlesBuildInputSpec
    output_spec = DipyRecoBundlesBuildOutputSpec

    # Static conservative placeholder; replaced by the tunable RAM estimator in a
    # later task (E3B, deferred).
    _mem_gb = STATIC_MEM_GB

    def _run_interface(self, runtime):
        from dipy.io.streamline import load_tractogram

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        out_pickle = self._gen_outfilename()

        previous = _pin_threads(num_threads)
        try:
            subject_sft = load_tractogram(
                self.inputs.tractogram_chunk, "same", bbox_valid_check=False
            )
            subject_sft.to_rasmm()
            rb = _build_recobundles(subject_sft.streamlines)
        finally:
            _restore_threads(previous)

        dump_build(rb, out_pickle)
        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_pickle
        if not isdefined(out_file):
            base = _strip_tractogram_ext(basename(self.inputs.tractogram_chunk))
            out_file = f"recobundles_{base}.pkl"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["recobundles_pickle"] = self._gen_outfilename()
        return outputs


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyRecoBundlesRecognizeInputSpec(BaseInterfaceInputSpec):
    recobundles_pickle = File(
        exists=True,
        mandatory=True,
        desc="lightweight built-RecoBundles pickle from DipyRecoBundlesBuild",
    )
    tractogram_chunk = File(
        exists=True,
        mandatory=True,
        desc="the same (sub-)tractogram (.trx) the build was made on -- its "
        "streamlines are reloaded here (they are not stored in the pickle)",
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
    # Scientific recognition parameters, never tuned for RAM. The defaults are
    # RECOGNITION_DEFAULTS, so the node runs standalone at the shipped
    # configuration; the bundle workflow sets them per tract through
    # recognition_params().
    reduction_thr = traits.Float(
        RECOGNITION_DEFAULTS["reduction_thr"],
        usedefault=True,
        desc="scientific: search-space reduction distance (mm)",
    )
    pruning_thr = traits.Float(
        RECOGNITION_DEFAULTS["pruning_thr"],
        usedefault=True,
        desc="scientific: pruning distance (mm)",
    )
    model_clust_thr = traits.Float(
        RECOGNITION_DEFAULTS["model_clust_thr"],
        usedefault=True,
        desc="scientific: model-bundle clustering MDF threshold (mm)",
    )
    refine = traits.Bool(
        RECOGNITION_DEFAULTS["refine"],
        usedefault=True,
        desc="scientific: run dipy's auto-calibration (refine) pass after the "
        "first recognition -- it rebuilds the search space from the subject's "
        "own first-pass bundle instead of the atlas model",
    )
    r_reduction_thr = traits.Float(
        RECOGNITION_DEFAULTS["r_reduction_thr"],
        usedefault=True,
        desc="scientific: refine-pass reduction distance (mm)",
    )
    r_pruning_thr = traits.Float(
        RECOGNITION_DEFAULTS["r_pruning_thr"],
        usedefault=True,
        desc="scientific: refine-pass pruning distance (mm)",
    )
    slr = traits.Bool(
        True,
        usedefault=True,
        desc="run RecoBundles' local (per-bundle) SLR in single-pass mode, used "
        "to select the bundle streamlines; it does not move the written output",
    )
    out_bundle = File(desc="the recognised bundle output (.trx)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyRecoBundlesRecognizeOutputSpec(TraitedSpec):
    recognized_bundle = File(
        desc="the recognised bundle in atlas space (.trx); empty-but-valid when "
        "the model shape is absent from the tractogram"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyRecoBundlesRecognize(BaseInterface):
    """
    Recognises one named HCP842 atlas bundle inside an atlas-space
    (sub-)tractogram by reloading a :class:`DipyRecoBundlesBuild` pickle (plus
    the same ``.trx`` streamlines) and running dipy's ``recognize`` for the model
    bundle addressed by explicit filename. Writes the recognised streamlines
    (atlas space) to a ``.trx`` file; the written streamlines are the subject's
    own, not the copies the local SLR moves into the model frame. Bringing the
    bundle back to reference space is
    :class:`~swane.nipype_pipeline.nodes.DipyBundlesToRef.DipyBundlesToRef`'s job.

    """

    input_spec = DipyRecoBundlesRecognizeInputSpec
    output_spec = DipyRecoBundlesRecognizeOutputSpec

    # Standalone static reservation; in the bundle workflow RAM is reserved from
    # the chunk's point count by RecoBundlesRamEstimator at scheduling time.
    _mem_gb = 2.0

    def _run_interface(self, runtime):
        from dipy.io.streamline import load_tractogram, save_tractogram
        from dipy.io.stateful_tractogram import StatefulTractogram
        from dipy.tracking.streamline import Streamlines

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
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

        previous = _pin_threads(num_threads)
        try:
            subject_sft = load_tractogram(
                self.inputs.tractogram_chunk, "same", bbox_valid_check=False
            )
            subject_sft.to_rasmm()
            rb = load_build(subject_sft.streamlines, self.inputs.recobundles_pickle)
            recognized, labels = _run_recognize(
                rb,
                model_bundle,
                model_clust_thr=float(self.inputs.model_clust_thr),
                reduction_thr=float(self.inputs.reduction_thr),
                pruning_thr=float(self.inputs.pruning_thr),
                slr=bool(self.inputs.slr),
                num_threads=num_threads,
            )
            # The auto-calibration pass, skipped when there is nothing to
            # calibrate on: dipy clusters the first-pass bundle, which is not
            # meaningful for a single streamline (and the bundles that recover
            # that little are a reported gap, not something refine can fix).
            if (
                bool(self.inputs.refine)
                and len(recognized) >= MIN_STREAMLINES_FOR_REFINE
            ):
                recognized, labels = _run_refine(
                    rb,
                    model_bundle,
                    recognized,
                    model_clust_thr=float(self.inputs.model_clust_thr),
                    r_reduction_thr=float(self.inputs.r_reduction_thr),
                    r_pruning_thr=float(self.inputs.r_pruning_thr),
                )
        finally:
            _restore_threads(previous)

        # The bundle is written as the subject streamlines the recognition
        # selected, copied into a new sequence, rather than as the copies the
        # local SLR moved into the model frame.
        bundle = Streamlines(subject_sft.streamlines[i] for i in labels)
        recognized_sft = StatefulTractogram.from_sft(bundle, model_sft)
        save_tractogram(recognized_sft, out_bundle, bbox_valid_check=False)

        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_bundle
        if not isdefined(out_file):
            base = _strip_tractogram_ext(basename(self.inputs.tractogram_chunk))
            name = str(self.inputs.model_bundle_name)
            out_file = f"recognized_{name}_{base}.trx"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["recognized_bundle"] = self._gen_outfilename()
        return outputs


def _strip_tractogram_ext(base):
    """Drop a trailing ``.trx``/``.trk``/``.tck`` extension from ``base``."""
    for ext in (".trx", ".trk", ".tck"):
        if base.endswith(ext):
            return base[: -len(ext)]
    return base
