# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
import numpy as np
import nibabel as nib
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)
from nipype import logging
from threadpoolctl import threadpool_limits

iflogger = logging.getLogger("nipype.interface")

ACF_THRESHOLD = 1.0 / np.e


def variance_normalise(data_4d, mask_3d):
    """Masked (Voxels, Time) matrix, each voxel's timecourse zero-mean/unit-var."""
    Y = data_4d[mask_3d].astype(np.float64)
    Y = Y - Y.mean(axis=1, keepdims=True)
    sd = Y.std(axis=1, keepdims=True)
    sd[sd == 0] = 1.0
    return Y / sd


def spatial_subsample_factor(data_4d, mask_3d, threshold=ACF_THRESHOLD, max_lag=15):
    """Data-driven i.i.d. correction factor f = Dx*Dy*Dz, where Di is the spatial
    decorrelation lag along axis i: the first lag where the spatial
    autocorrelation of the temporal fluctuations drops below ``threshold``.

    This is a variant of the i.i.d. subsampling of Li et al. 2007, which
    estimates the depth with an entropy-rate measure instead. The 1/e
    crossing (e-folding length) is a convention with no published source for
    this use, and the resulting model order depends on it."""
    # Remove the anatomical mean image: keep only temporal fluctuations.
    d = data_4d.copy()
    d[mask_3d] = data_4d[mask_3d] - data_4d[mask_3d].mean(axis=1, keepdims=True)

    def decorrelation_lag(axis):
        for lag in range(1, max_lag):
            s1 = [slice(None)] * 3
            s2 = [slice(None)] * 3
            s1[axis] = slice(None, -lag)
            s2[axis] = slice(lag, None)
            valid = mask_3d[tuple(s1)] & mask_3d[tuple(s2)]
            if not np.any(valid):
                return lag
            v1 = d[tuple(s1)][valid].astype(np.float64)  # (Vpairs, T)
            v2 = d[tuple(s2)][valid].astype(np.float64)
            v1n = (v1 - v1.mean(0, keepdims=True)) / (v1.std(0, keepdims=True) + 1e-12)
            v2n = (v2 - v2.mean(0, keepdims=True)) / (v2.std(0, keepdims=True) + 1e-12)
            acf = np.mean(np.sum(v1n * v2n, axis=0) / v1.shape[0])
            if acf < threshold:
                return lag
        return max_lag

    dx, dy, dz = decorrelation_lag(0), decorrelation_lag(1), decorrelation_lag(2)
    return float(dx * dy * dz), (dx, dy, dz)


def estimate_dim_mdl(Y, subsample_factor, rank_max=None):
    """MDL model order over the temporal covariance eigenvalues, with the
    effective sample size N_eff = N / f. Returns the k minimising MDL(k).

    rank_max, when given, caps the numerical rank at the rank of a regression
    already applied to the data (including its constant column). Those
    removed directions have ~0 eigenvalues that float32 round-off lifts above
    the numerical-rank tolerance, which collapses the geometric/arithmetic
    tail ratio used by the MDL criterion and makes the estimate explode; they
    are excluded explicitly by capping the eigenvalue set. With
    rank_max=None the eigenvalue set is only cut by the tolerance, as before.

    References:
    - Li Y-O, Adali T, Calhoun VD (2007). Estimating the number of independent
      components for functional magnetic resonance imaging data. Hum Brain Mapp 28:1251-1266.
    - Beckmann CF, Smith SM (2004). Probabilistic Independent Component Analysis
      for Functional Magnetic Resonance Imaging. IEEE TMI 23:137-152 §II.
    """
    N, T = Y.shape
    N_eff = N / subsample_factor
    Yc = Y - Y.mean(axis=0, keepdims=True)
    cov = (Yc.T @ Yc) / (N - 1)
    ev = np.linalg.eigvalsh(cov)[::-1]
    tol = ev.max() * max(Y.shape) * np.finfo(ev.dtype).eps
    rank = int(np.sum(ev > tol))
    if rank_max is not None:
        rank = max(min(rank, int(rank_max)), 0)
    if rank == 0:
        return 0
    mdl = np.full(rank, np.inf)
    for k in range(rank - 1):
        tail = ev[k + 1 : rank]
        ratio = np.exp(np.mean(np.log(tail))) / np.mean(tail)  # geo/arith mean
        if ratio <= 0:
            continue
        mdl[k] = -N_eff * (rank - k) * np.log(ratio) + 0.5 * k * (
            2 * rank - k
        ) * np.log(N_eff)
    return int(np.argmin(mdl))


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class NilearnAutoDimInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="Any unsmoothed 4D series")
    mask_file = File(exists=True, mandatory=True, desc="Tight 3D brain mask")
    n_removed = traits.Int(
        0,
        usedefault=True,
        desc="Rank of a regression already applied to in_file (including its "
        "constant column). When > 0, caps the numerical rank used by the MDL "
        "estimate at n_timepoints - n_removed.",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the covariance eigenvalues"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class NilearnAutoDimOutputSpec(TraitedSpec):
    n_components = traits.Int(desc="Estimated number of components")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class NilearnAutoDim(BaseInterface):
    """
    MDL model-order on any unsmoothed 4D series with a tight (pre-dilation)
    BOLD mask. When the series is the residual of a regression already
    applied upstream, n_removed caps the numerical rank at the regression's
    rank so the removed near-zero eigenvalues do not inflate the estimate.

    References:
    - Li Y-O, Adali T, Calhoun VD (2007). Estimating the number of independent
      components for functional magnetic resonance imaging data. Hum Brain Mapp 28:1251-1266.
    - Wax M, Kailath T (1985). Detection of signals by information theoretic
      criteria. IEEE Trans Acoust Speech Signal Process 33(2):387-392,
      https://doi.org/10.1109/TASSP.1985.1164557 (the MDL formula, used by
      Li et al. 2007 above).
    - Beckmann CF, Smith SM (2004). Probabilistic Independent Component Analysis
      for Functional Magnetic Resonance Imaging. IEEE TMI 23:137-152 §II.
    """

    input_spec = NilearnAutoDimInputSpec
    output_spec = NilearnAutoDimOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        data = nib.load(self.inputs.in_file).get_fdata()
        mask = nib.load(self.inputs.mask_file).get_fdata() > 0

        f, lags = spatial_subsample_factor(data, mask)
        Y = variance_normalise(data, mask)
        n_removed = self.inputs.n_removed
        if n_removed > 0:
            rank_max = Y.shape[1] - n_removed
            if rank_max < 1:
                iflogger.warning(
                    "NilearnAutoDim: the upstream regression removed %d "
                    "directions from %d timepoints, no rank is left for the "
                    "model-order estimate; using 1 component",
                    n_removed,
                    Y.shape[1],
                )
            dim = estimate_dim_mdl(Y, f, rank_max=rank_max)
        else:
            dim = estimate_dim_mdl(Y, f)
        dim = max(int(dim), 1)

        self._n_components = dim
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["n_components"] = self._n_components
        return outputs
