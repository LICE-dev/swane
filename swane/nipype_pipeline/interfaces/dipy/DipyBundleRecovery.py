"""Per-bundle runtime recovery for RecoBundles recognition.

RecoBundles recognises each tract with one configuration (see
:mod:`~swane.nipype_pipeline.interfaces.dipy.DipyRecoBundles`), but the same configuration
is not right for every subject: on some the bundle comes out **contaminated**
(many streamlines far from the atlas model), on others **scarce** (little of the
model covered), and on the good ones it is already fine. Rather than a per-tract
override -- which cannot adapt per subject -- this module scores the recognised
bundle against the atlas model and, when it looks off, retries recognition once
with an adjusted configuration and keeps whichever result matches the model
better. A bundle that stays poor after the retry is flagged low-confidence
instead of being silently shipped.

The two levers, and the mechanism each addresses:

* **contamination** -- precision (fraction of recognised streamlines within
  :data:`PR_THR_MM` of the model) is low while recall (fraction of the model
  covered) is not: the bundle overshoots the model. Retrying with a **tighter**
  refine pruning trims the overshoot.
* **scarcity** -- recall is low: the bundle undershoots the model. Retrying with
  a **wider** first-pass reduction can pick up more of it. When recall stays low
  whatever the configuration the shortfall is upstream (tracking/registration),
  not something recognition can invent, so the bundle is flagged, not widened
  further.

The accept rule is symmetric and self-guarding: keep the retried result only if
its recall/precision harmonic mean (F) beats the original, so a retry that
collapses the bundle is never kept. Every threshold is a named constant so it can
be retuned in one place.
"""

import json
from os.path import abspath

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    Directory,
    InputMultiPath,
    isdefined,
)

from swane.nipype_pipeline.interfaces.dipy.DipyRecoBundles import (
    RECOGNITION_DEFAULTS,
    bundle_path,
    recognize_chunk,
)

# --- metric --------------------------------------------------------------- #
# A recognised/model streamline "matches" the other bundle when its MDF to the
# nearest streamline there is under this (mm). Both bundles are resampled to
# PR_POINTS points for the (equal-length) MDF. A large recognised bundle is
# subsampled to at most PR_CAP streamlines for the distance matrix, with a fixed
# seed so the score is reproducible.
PR_THR_MM = 5.0
PR_POINTS = 20
PR_CAP = 5000
METRIC_RNG_SEED = 2024

# --- recovery gate -------------------------------------------------------- #
# Contamination: precision below PREC_CONTAMINATED while recall stays above
# REC_PRESENT (the bundle is there, just overshooting) -> try a tighter refine
# pruning. Scarcity: recall below REC_PRESENT -> try a wider first-pass
# reduction. A bundle left below these on both axes covers little of the model
# and is flagged low-confidence.
PREC_CONTAMINATED = 0.20
REC_PRESENT = 0.25
# The adjusted thresholds a retry uses: a tighter refine pruning to trim an
# over-inclusive bundle, a wider first-pass reduction to pick up more of a sparse
# one.
TIGHTEN_R_PRUNING_THR = 4.0
WIDEN_REDUCTION_THR = 25.0
# Below this recognised-streamline count a bundle is treated as empty for the
# metric and flagged: too few streamlines to represent the tract.
MIN_COUNT = 10


def precision_recall_f5(recognized, model):
    """Precision, recall and their harmonic mean between a recognised bundle and
    the atlas model, at :data:`PR_THR_MM`.

    Parameters
    ----------
    recognized : sequence of ndarray
        The recognised streamlines (Nx3 arrays), in the atlas model space.
    model : sequence of ndarray
        The atlas model-bundle streamlines, same space.

    Returns
    -------
    precision, recall, f5 : float
        precision = fraction of recognised streamlines with a model streamline
        within :data:`PR_THR_MM`; recall = fraction of model streamlines with a
        recognised streamline within :data:`PR_THR_MM`; f5 = their harmonic mean
        (0 when either is 0). All rounded to 4 decimals. An empty recognised or
        model bundle yields ``(0.0, 0.0, 0.0)``.
    """
    from dipy.tracking.streamline import set_number_of_points
    from dipy.tracking.distances import bundles_distances_mdf

    if len(recognized) == 0 or len(model) == 0:
        return 0.0, 0.0, 0.0

    rec = recognized
    if len(rec) > PR_CAP:
        rng = np.random.default_rng(METRIC_RNG_SEED)
        keep = rng.choice(len(rec), PR_CAP, replace=False)
        rec = [rec[i] for i in keep]

    rec20 = set_number_of_points(rec, PR_POINTS)
    model20 = set_number_of_points(model, PR_POINTS)
    d = bundles_distances_mdf(rec20, model20)  # (n_rec, n_model)
    precision = float((d.min(axis=1) < PR_THR_MM).mean())
    recall = float((d.min(axis=0) < PR_THR_MM).mean())
    f5 = (
        0.0
        if precision + recall == 0
        else 2 * precision * recall / (precision + recall)
    )
    return round(precision, 4), round(recall, 4), round(f5, 4)


def recovery_arm(precision, recall):
    """Which retry a recognised bundle's metric calls for, or ``None``.

    ``"tighten"`` when it looks contaminated (precision below
    :data:`PREC_CONTAMINATED` but recall at/above :data:`REC_PRESENT`),
    ``"widen"`` when it looks scarce (recall below :data:`REC_PRESENT`), and
    ``None`` when it is already good enough to leave alone. The two arms are
    exclusive by construction.
    """
    if recall < REC_PRESENT:
        return "widen"
    if precision < PREC_CONTAMINATED:
        return "tighten"
    return None


def adjusted_params(params, arm):
    """A copy of ``params`` with the one threshold ``arm`` adjusts.

    ``"tighten"`` lowers ``r_pruning_thr`` to :data:`TIGHTEN_R_PRUNING_THR`;
    ``"widen"`` raises ``reduction_thr`` to :data:`WIDEN_REDUCTION_THR`. Any other
    ``arm`` returns an unchanged copy.
    """
    adjusted = dict(params)
    if arm == "tighten":
        adjusted["r_pruning_thr"] = TIGHTEN_R_PRUNING_THR
    elif arm == "widen":
        adjusted["reduction_thr"] = WIDEN_REDUCTION_THR
    return adjusted


def is_low_confidence(precision, recall, count):
    """Whether a bundle should be flagged after recovery.

    True when it covers little of the model however it was recognised: fewer than
    :data:`MIN_COUNT` streamlines, or both precision and recall below their gate
    thresholds (a displaced/absent bundle, an upstream gap recognition cannot
    fix). These are shipped with a flag rather than silently.
    """
    if count < MIN_COUNT:
        return True
    return precision < PREC_CONTAMINATED and recall < REC_PRESENT


# --- node ----------------------------------------------------------------- #


def _recognized_metric(streamlines, model_bundle):
    """(precision, recall, f5, count) of a recognised bundle against the model."""
    prec, rec, f5 = precision_recall_f5(streamlines, model_bundle)
    return prec, rec, f5, len(streamlines)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyBundleRecoveryInputSpec(BaseInterfaceInputSpec):
    default_bundle = File(
        exists=True,
        mandatory=True,
        desc="the bundle recognised with the default configuration (.trx, atlas "
        "space), the union of the per-chunk recognitions -- scored, and kept "
        "unless a retry matches the model better",
    )
    recobundles_pickles = InputMultiPath(
        File(exists=True),
        mandatory=True,
        desc="the per-chunk RecoBundles build pickles, for a retry recognition",
    )
    tractogram_chunks = InputMultiPath(
        File(exists=True),
        mandatory=True,
        desc="the per-chunk subject tractograms (.trx) the builds were made on",
    )
    atlas_dir = Directory(
        mandatory=True, desc="local DIPY_HOME holding the HCP842 atlas"
    )
    model_bundle_name = traits.Str(
        mandatory=True,
        desc="atlas bundle basename without extension, e.g. 'IFOF_R'",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for a retry recognition"
    )
    # The default configuration this bundle was recognised with; a retry adjusts
    # one threshold of it (see :func:`adjusted_params`).
    reduction_thr = traits.Float(RECOGNITION_DEFAULTS["reduction_thr"], usedefault=True)
    pruning_thr = traits.Float(RECOGNITION_DEFAULTS["pruning_thr"], usedefault=True)
    model_clust_thr = traits.Float(
        RECOGNITION_DEFAULTS["model_clust_thr"], usedefault=True
    )
    refine = traits.Bool(RECOGNITION_DEFAULTS["refine"], usedefault=True)
    r_reduction_thr = traits.Float(
        RECOGNITION_DEFAULTS["r_reduction_thr"], usedefault=True
    )
    r_pruning_thr = traits.Float(RECOGNITION_DEFAULTS["r_pruning_thr"], usedefault=True)
    slr = traits.Bool(True, usedefault=True)
    out_bundle = File(desc="the chosen bundle output (.trx)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyBundleRecoveryOutputSpec(TraitedSpec):
    bundle = File(
        desc="the chosen bundle in atlas space (.trx): the default, or a retry "
        "that matched the model better"
    )
    confidence_flag = File(
        desc="a JSON sidecar written ONLY when the chosen bundle is low-confidence "
        "(covers little of the model whatever the configuration); Undefined "
        "otherwise, so DataSink sinks it only when present"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyBundleRecovery(BaseInterface):
    """Score a recognised bundle against the atlas model and, when it looks
    contaminated or scarce, retry recognition once with an adjusted configuration,
    keeping whichever result matches the model better; flag one that stays poor.

    See the module docstring for the two levers and the accept rule. The retry
    re-recognises every chunk in turn with :func:`recognize_chunk`, so it holds at
    most one chunk in memory and matches a first-pass recognition exactly.
    """

    input_spec = DipyBundleRecoveryInputSpec
    output_spec = DipyBundleRecoveryOutputSpec

    def _run_interface(self, runtime):
        from dipy.io.streamline import load_tractogram, save_tractogram
        from dipy.io.stateful_tractogram import StatefulTractogram
        from dipy.tracking.streamline import Streamlines

        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )

        model_file = bundle_path(self.inputs.atlas_dir, self.inputs.model_bundle_name)
        model_sft = load_tractogram(model_file, "same", bbox_valid_check=False)
        model_sft.to_rasmm()
        model_bundle = model_sft.streamlines

        # Score the default recognition (the union of the per-chunk bundles).
        default_sft = load_tractogram(
            self.inputs.default_bundle, "same", bbox_valid_check=False
        )
        default_sft.to_rasmm()
        chosen = default_sft.streamlines
        prec, rec, f5, count = _recognized_metric(chosen, model_bundle)
        arm = recovery_arm(prec, rec)

        # One adjusted retry, kept only if it matches the model better.
        if arm is not None:
            params = {
                "model_clust_thr": float(self.inputs.model_clust_thr),
                "reduction_thr": float(self.inputs.reduction_thr),
                "pruning_thr": float(self.inputs.pruning_thr),
                "refine": bool(self.inputs.refine),
                "r_reduction_thr": float(self.inputs.r_reduction_thr),
                "r_pruning_thr": float(self.inputs.r_pruning_thr),
            }
            retry_params = adjusted_params(params, arm)
            retry = Streamlines()
            for chunk, pickle in zip(
                self.inputs.tractogram_chunks, self.inputs.recobundles_pickles
            ):
                retry.extend(
                    recognize_chunk(
                        chunk,
                        pickle,
                        model_bundle,
                        retry_params,
                        slr=bool(self.inputs.slr),
                        num_threads=num_threads,
                    )
                )
            r_prec, r_rec, r_f5, r_count = _recognized_metric(retry, model_bundle)
            if r_f5 > f5:
                chosen, prec, rec, f5, count = retry, r_prec, r_rec, r_f5, r_count

        save_tractogram(
            StatefulTractogram.from_sft(chosen, model_sft),
            self._gen_outfilename(),
            bbox_valid_check=False,
        )

        self._flag_written = is_low_confidence(prec, rec, count)
        if self._flag_written:
            with open(self._gen_flagname(), "w") as flag_file:
                json.dump(
                    {
                        "model_bundle": str(self.inputs.model_bundle_name),
                        "precision": prec,
                        "recall": rec,
                        "f5": f5,
                        "count": count,
                        "retry_arm": arm,
                        "low_confidence": True,
                    },
                    flag_file,
                    indent=1,
                )
        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_bundle
        if not isdefined(out_file):
            out_file = "recovered_%s.trx" % str(self.inputs.model_bundle_name)
        return abspath(out_file)

    def _gen_flagname(self):
        base = self._gen_outfilename()
        for ext in (".trx", ".trk", ".tck"):
            if base.endswith(ext):
                base = base[: -len(ext)]
                break
        return base + ".lowconf.json"

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["bundle"] = self._gen_outfilename()
        if getattr(self, "_flag_written", False):
            outputs["confidence_flag"] = self._gen_flagname()
        return outputs
