# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import json
import os
import warnings

import numpy as np
import nibabel as nib
from nipype import logging
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)
from threadpoolctl import threadpool_limits
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform
from sklearn.exceptions import ConvergenceWarning

iflogger = logging.getLogger("nipype.interface")


def _variance_normalise(data_4d, mask_3d):
    """Masked (Voxels, Time) matrix, each voxel's timecourse zero-mean/unit-var.

    References:
    - Beckmann CF, Smith SM (2004). Probabilistic Independent Component Analysis
      for Functional Magnetic Resonance Imaging. IEEE TMI 23:137-152 SS II.
    """
    Y = data_4d[mask_3d].astype(np.float64)
    Y = Y - Y.mean(axis=1, keepdims=True)
    sd = Y.std(axis=1, keepdims=True)
    sd[sd == 0] = 1.0
    return Y / sd


def fastica_run(X_vt, K, seed, fun="cube", max_iter=10000, tol=1e-4):
    """One spatial FastICA fit: samples = voxels, features = time.

    Returns maps (V,K) and time courses (T,K) oriented to positive skew, the
    unmixing matrix W (K,K) in whitened space, the number of iterations used,
    and whether sklearn's convergence criterion was met.

    References:
    - Hyvarinen A (1999). Fast and robust fixed-point algorithms for
      independent component analysis. IEEE TNN 10:626-634.
    """
    from sklearn.decomposition import FastICA

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        ica = FastICA(
            n_components=K,
            algorithm="parallel",
            whiten="unit-variance",
            fun=fun,
            max_iter=max_iter,
            tol=tol,
            random_state=int(seed),
            whiten_solver="eigh",
        )
        S = ica.fit_transform(X_vt)  # (V, K)
    A = ica.mixing_  # (T, K)

    # Sign convention: positive skew (heavy tail positive).
    sk = np.sign(((S - S.mean(0)) ** 3).mean(0))
    sk[sk == 0] = 1
    S, A = S * sk, A * sk
    W = ica._unmixing * sk[:, None]  # (K, K) unmixing in whitened space

    convergence_warnings = [
        str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)
    ]
    return {
        "maps": S,
        "tc": A,
        "W": W,
        "n_iter": int(ica.n_iter_),
        "converged": len(convergence_warnings) == 0,
        "warnings": convergence_warnings,
    }


def _abs_corr_between_runs(runs_maps):
    """Stacked |r| matrix (N*K, N*K) between every component of every run, and
    the run label of each row.

    References:
    - Himberg J, Hyvarinen A, Esposito F (2004). Validating the independent
      components of neuroimaging time series via clustering and visualization.
      NeuroImage 22:1214-1222.
    """
    M = np.concatenate([m.T for m in runs_maps], axis=0)  # (N*K, V)
    Mc = M - M.mean(axis=1, keepdims=True)
    sd = Mc.std(axis=1, keepdims=True)
    sd[sd == 0] = 1e-12
    Z = Mc / sd
    R = np.abs(Z @ Z.T / Z.shape[1])
    labels = np.repeat(np.arange(len(runs_maps)), runs_maps[0].shape[1])
    return R, labels


def _icasso_clusters(R, K):
    """Average-linkage clustering of the |r| affinity into K clusters (ICASSO).

    References:
    - Himberg J, Hyvarinen A, Esposito F (2004). NeuroImage 22:1214-1222.
    """
    if R.shape[0] < 2:
        # A single map (one run, one component) is its own cluster.
        return np.zeros(R.shape[0], dtype=int)
    # |r| can exceed 1 by floating-point round-off between identical maps;
    # a distance is never negative.
    D = np.clip(1.0 - R, 0.0, None)
    np.fill_diagonal(D, 0.0)
    D = (D + D.T) / 2
    Z = linkage(squareform(D, checks=False), method="average")
    return fcluster(Z, K, criterion="maxclust") - 1


def _iq_per_cluster(R, cl):
    """ICASSO cluster quality index Iq: mean intra-cluster |r| minus mean |r|
    to the rest of the components.

    References:
    - Himberg J, Hyvarinen A, Esposito F (2004). NeuroImage 22:1214-1222.
    """
    out = {}
    for c in np.unique(cl):
        m = cl == c
        n = m.sum()
        intra = (R[np.ix_(m, m)].sum() - n) / (n * (n - 1)) if n > 1 else 1.0
        extra = R[np.ix_(m, ~m)].mean() if (~m).any() else 0.0
        out[int(c)] = float(intra - extra)
    return out


def amari_index(P):
    """Amari et al. 1996 performance index of a (near-)permutation matrix P.

    References:
    - Amari S, Cichocki A, Yang HH (1996). A new learning algorithm for blind
      signal separation. NIPS 8.
    """
    P = np.abs(P)
    K = P.shape[0]
    if K < 2:
        # A 1x1 matrix is always a scaled permutation: no cross-talk.
        return 0.0
    a = (P / P.max(axis=1, keepdims=True)).sum(axis=1) - 1
    b = (P / P.max(axis=0, keepdims=True)).sum(axis=0) - 1
    return float((a.sum() + b.sum()) / (2 * K * (K - 1)))


def select_cross_isi(Ws):
    """Run with the smallest mean Amari index to every other run's unmixing
    matrix (same whitening space).

    References:
    - Long Q, et al. (2018). ICASSP.
    - Amari S, Cichocki A, Yang HH (1996). NIPS 8.
    """
    N = len(Ws)
    if N < 2:
        # A single run has no other run to compare with.
        return 0, [0.0] * N
    isi = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            if i != j:
                isi[i, j] = amari_index(Ws[i] @ np.linalg.inv(Ws[j]))
    m = isi.sum(axis=1) / (N - 1)
    return int(np.argmin(m)), m.tolist()


def data_rank(X_vt):
    """Numerical rank of the (V, T) data: the number of temporal covariance
    eigenvalues above ``max * max(V, T) * eps``, the same tolerance as the
    model-order estimate. Spatial FastICA cannot extract more components."""
    ev = np.linalg.eigvalsh(X_vt.T @ X_vt)
    tol = ev.max() * max(X_vt.shape) * np.finfo(ev.dtype).eps
    return int(np.sum(ev > tol))


def icasso(X_vt, K, n_runs, random_state, max_iter, tol, fun="cube"):
    """ICASSO over `n_runs` FastICA fits with seeds-only diversity: |r|
    clustering (average linkage), then the run with the minimum mean
    cross-run Amari index (cross-ISI, Long 2018) is selected.

    References:
    - Hyvarinen A (1999). IEEE TNN 10:626-634.
    - Himberg J, Hyvarinen A, Esposito F (2004). NeuroImage 22:1214-1222.
    - Long Q, et al. (2018). ICASSP.
    - Amari S, Cichocki A, Yang HH (1996). NIPS 8.
    """
    seeds = np.random.SeedSequence(random_state).generate_state(n_runs)
    runs = [
        fastica_run(X_vt, K, seed, fun=fun, max_iter=max_iter, tol=tol)
        for seed in seeds
    ]

    for i, r in enumerate(runs):
        if not r["converged"]:
            iflogger.warning(
                "FastIcaIcasso run %d/%d reached max_iter=%d without converging "
                "(n_iter=%d): %s",
                i + 1,
                n_runs,
                max_iter,
                r["n_iter"],
                "; ".join(r["warnings"]),
            )

    R, labels = _abs_corr_between_runs([r["maps"] for r in runs])
    cl = _icasso_clusters(R, K)
    iq = _iq_per_cluster(R, cl)
    best, cross_isi_scores = select_cross_isi([r["W"] for r in runs])
    maps = runs[best]["maps"]
    comp_iq = [iq[int(c)] for c in cl[labels == best]]

    report = {
        "n_runs": n_runs,
        "random_state": random_state,
        "n_iter": [r["n_iter"] for r in runs],
        "converged": [r["converged"] for r in runs],
        "selected_run": best,
        "cross_isi_scores": cross_isi_scores,
        "iq_per_cluster": {str(k): v for k, v in iq.items()},
        "selected_run_iq": comp_iq,
    }
    return maps, report


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class FastIcaIcassoInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        desc="Preprocessed 4D EPI (tight or dilated mask, per caller)",
    )
    mask_file = File(exists=True, mandatory=True, desc="Dilated 3D brain mask")
    n_components = traits.Int(mandatory=True, desc="Number of components")
    n_runs = traits.Int(
        10, usedefault=True, desc="Number of ICASSO FastICA runs (seeds only)"
    )
    max_iter = traits.Int(
        10000, usedefault=True, desc="Maximum FastICA iterations per run"
    )
    tol = traits.Float(1e-4, usedefault=True, desc="FastICA convergence tolerance")
    random_state = traits.Int(
        0,
        usedefault=True,
        desc="Seed for numpy.random.SeedSequence, which generates the per-run seeds",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the FastICA runs"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class FastIcaIcassoOutputSpec(TraitedSpec):
    components_file = File(desc="Selected run's spatial components")
    report_file = File(
        desc="JSON report: per-run n_iter/converged, selected run, cross-ISI scores, ICASSO Iq"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class FastIcaIcasso(BaseInterface):
    """
    Spatial FastICA with ICASSO run selection: per-voxel variance
    normalisation, `n_runs` FastICA fits (cube non-linearity, unit-variance
    whitening, eigh whitening solver) from independent seeds, |r| clustering
    (average linkage) between runs, and cross-ISI selection (the run with the
    smallest mean Amari index to every other run) of the output components.
    Each component is oriented so that its spatial map has positive skewness
    (the sign of an ICA component is arbitrary; convention as in Michael et
    al. 2014).

    A run that reaches `max_iter` without meeting sklearn's convergence
    criterion is recorded as not converged and logged as a node warning; it
    is never treated as a failure. A `n_components` above the numerical rank
    of the variance-normalised data (at most T - 1) is clamped to that rank,
    with a node warning stating both values; the report records both.

    A non-converging fit at K~34 components on ~65000 voxels can take on the
    order of an hour for 10 runs at `max_iter=10000`: set the node's RAM
    reservation and `num_threads` deliberately.
    The OpenMP/BLAS pools are capped at `num_threads` (1 when undefined, as
    Nipype reserves for the node).

    References:
    - Hyvarinen A (1999). Fast and robust fixed-point algorithms for
      independent component analysis. IEEE TNN 10:626-634.
    - Himberg J, Hyvarinen A, Esposito F (2004). Validating the independent
      components of neuroimaging time series via clustering and
      visualization. NeuroImage 22:1214-1222.
    - Long Q, et al. (2018). Consistent run selection for independent
      component analysis. ICASSP.
    - Amari S, Cichocki A, Yang HH (1996). A new learning algorithm for blind
      signal separation. NIPS 8.
    - Beckmann CF, Smith SM (2004). Probabilistic Independent Component
      Analysis for Functional Magnetic Resonance Imaging. IEEE TMI
      23:137-152 SS II.
    - Michael AM, Anderson M, Miller RL, Adali T, Calhoun VD (2014).
      Preserving subject variability in group fMRI analysis: performance
      evaluation of GICA vs. IVA. Front Syst Neurosci 8:106.
      doi:10.3389/fnsys.2014.00106
    """

    input_spec = FastIcaIcassoInputSpec
    output_spec = FastIcaIcassoOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        in_path = self.inputs.in_file
        mask_path = self.inputs.mask_file
        K = self.inputs.n_components
        out_dir = runtime.cwd

        mask_img = nib.load(mask_path)
        mask_data = mask_img.get_fdata() > 0
        data = nib.load(in_path).get_fdata()

        X_vt = _variance_normalise(data, mask_data)
        K_requested = K
        rank = data_rank(X_vt)
        if rank < 1:
            raise ValueError(
                "FastIcaIcasso: the masked data have no temporal variance, "
                "no component can be extracted"
            )
        if K > rank:
            iflogger.warning(
                "FastIcaIcasso: %d components requested but the data rank is "
                "%d (after removing each voxel's temporal mean); using %d "
                "components",
                K_requested,
                rank,
                rank,
            )
            K = rank
        maps, report = icasso(
            X_vt,
            K,
            n_runs=self.inputs.n_runs,
            random_state=self.inputs.random_state,
            max_iter=self.inputs.max_iter,
            tol=self.inputs.tol,
        )

        report["n_components_requested"] = int(K_requested)
        report["n_components"] = int(K)

        comp_vol = np.zeros(mask_img.shape + (K,), dtype=np.float32)
        comp_vol[mask_data] = maps.astype(np.float32)
        comp_path = os.path.join(out_dir, "ica_IC.nii.gz")
        nib.save(nib.Nifti1Image(comp_vol, mask_img.affine, mask_img.header), comp_path)
        self._components_file = comp_path

        report_path = os.path.join(out_dir, "icasso_report.json")
        with open(report_path, "w") as fh:
            json.dump(report, fh, indent=1)
        self._report_file = report_path

        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["components_file"] = self._components_file
        outputs["report_file"] = self._report_file
        return outputs
