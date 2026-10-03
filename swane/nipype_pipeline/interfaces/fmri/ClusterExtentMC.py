# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import json
import os
import time

import nibabel as nib
import numpy as np
from nipype import logging
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    File,
    TraitedSpec,
    traits,
    isdefined,
)
from threadpoolctl import threadpool_limits
from scipy import ndimage
from scipy.optimize import curve_fit

iflogger = logging.getLogger("nipype.interface")

# FWHM of a Gaussian ACF exp(-r^2 / (2 b^2)): FWHM = 2 sqrt(2 ln 2) b
# (Cox et al. 2017, eq. 2).
FWHM_PER_B = 2.0 * np.sqrt(2.0 * np.log(2.0))


def acf_model(r, a, b, c):
    """Mixed Gaussian + mono-exponential spatial ACF (Cox et al. 2017, eq. 3):
    h(r) = a exp(-r^2 / (2 b^2)) + (1 - a) exp(-r / c)."""
    return a * np.exp(-(r**2) / (2 * b**2)) + (1 - a) * np.exp(-r / c)


def _lag_mm(pshape, zooms):
    """Distance in mm of each (circular) lag on a padded FFT grid."""
    ax = [
        np.where(np.arange(n) < (n + 1) // 2, np.arange(n), np.arange(n) - n) * z
        for n, z in zip(pshape, zooms)
    ]
    gx, gy, gz = np.meshgrid(*ax, indexing="ij")
    return np.sqrt(gx**2 + gy**2 + gz**2)


def empirical_acf(R_vt, dmask, zooms, n_vol=60, min_pairs=1000, r_max_mm=30.0):
    """Mask-normalised spatial autocorrelation of residual volumes, binned by
    distance.

    Each voxel is scaled to unit temporal variance; for up to ``n_vol`` evenly
    spaced volumes the spatially demeaned volume is autocorrelated through
    the FFT (Wiener-Khinchin) on a zero-padded grid (linear, not circular
    lags) and divided by the number of voxel pairs inside the mask at each
    lag (masked FFT correlation with FFT-computed overlap counts, as in
    Padfield 2012). Lags with ``min_pairs`` pairs or fewer are skipped. The
    ACF is normalised to 1 at lag 0 and averaged in 1 mm distance bins up to
    ``r_max_mm``. ``n_vol``, ``min_pairs``, the bin width and ``r_max_mm``
    are design parameters; on synthetic residuals with the mixed ACF the
    resulting k did not change for n_vol 20-150, r_max_mm 20-45 or
    min_pairs 100-10000.

    Returns the bin distances (mm) and ACF values, starting with (0, 1).
    When no ACF can be measured (residuals with zero variance, or lag 0
    itself has too few pairs) only the lag-0 point is returned.
    """
    R = R_vt / (R_vt.std(1, keepdims=True) + 1e-12)
    pshape = tuple(2 * s for s in dmask.shape)  # zero padding: linear, not circular
    m = dmask.astype(np.float64)
    npairs = np.fft.irfftn(np.abs(np.fft.rfftn(m, pshape)) ** 2, pshape)
    acc = np.zeros(pshape)
    ts = np.linspace(0, R.shape[1] - 1, min(n_vol, R.shape[1])).astype(int)
    for t in ts:
        x = np.zeros(dmask.shape)
        x[dmask] = R[:, t] - R[:, t].mean()
        acc += np.fft.irfftn(np.abs(np.fft.rfftn(x, pshape)) ** 2, pshape)
    ok = npairs > min_pairs
    acf = np.zeros(pshape)
    acf[ok] = acc[ok] / npairs[ok]
    if not (ok[0, 0, 0] and np.isfinite(acf[0, 0, 0]) and acf[0, 0, 0] > 0):
        return np.array([0.0]), np.array([1.0])
    acf /= acf[0, 0, 0]
    r = _lag_mm(pshape, zooms)
    edges = np.arange(0.0, r_max_mm + 1.0, 1.0)
    rc, vc = [0.0], [1.0]
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = ok & (r > lo) & (r <= hi)
        if sel.sum():
            rc.append(float(r[sel].mean()))
            vc.append(float(acf[sel].mean()))
    return np.array(rc), np.array(vc)


def fit_acf(rc, vc):
    """Bounded least-squares fit of ``acf_model`` to the binned ACF.

    Returns ``[a, b, c]`` (b and c in mm) and the RMSE of the fit. Raises
    ValueError when there are fewer than four ACF points (three parameters
    plus one residual degree of freedom), and whatever
    ``scipy.optimize.curve_fit`` raises when the fit fails.
    """
    if len(rc) < 4:
        raise ValueError(f"{len(rc)} ACF points, at least 4 are needed")
    p, _ = curve_fit(
        acf_model,
        rc,
        vc,
        p0=[0.5, 3.0, 5.0],
        bounds=([0.0, 0.1, 0.1], [1.0, 50.0, 200.0]),
        maxfev=20000,
    )
    rmse = float(np.sqrt(np.mean((acf_model(rc, *p) - vc) ** 2)))
    return [float(x) for x in p], rmse


def empirical_acf_function(rc, vc):
    """Piecewise-linear ACF through the binned values, 0 beyond the last bin.
    Used as the null-field ACF when the parametric fit fails."""
    rc = np.asarray(rc, float)
    vc = np.asarray(vc, float)
    return lambda r: np.interp(r, rc, vc, right=0.0)


def null_fields(a, b, c, dmask, zooms, n, seed=0, acf=None, acf_extent_mm=0.0):
    """Generator of ``n`` Gaussian random fields with ACF h(r), restricted to
    the mask and spatially standardised (zero mean, unit SD over the mask).

    White N(0,1) noise on a grid padded by ``min(20, ceil(3 max(b, c) /
    voxel))`` voxels per axis is filtered in Fourier space with the square
    root of the power spectrum of h(r) (negative spectral values clipped to
    0), then cropped back to the mask grid: approximate circulant embedding
    (Wood and Chan 1994; Dietrich and Newsam 1997), where the padding keeps
    the periodic wrap-around correlation below (1 - a) exp(-6). The 20-voxel
    cap is a design parameter that binds only for very long ACF tails.
    ``acf`` (a callable of the distance in mm) replaces the parametric
    h(r); the padding then covers its support ``acf_extent_mm``, with the
    same 20-voxel cap.
    """
    if acf is None:
        extent_mm = 3 * max(b, c)
        acf = lambda r: acf_model(r, a, b, c)  # noqa: E731
    else:
        extent_mm = acf_extent_mm
    marg = [int(min(20, np.ceil(extent_mm / z))) for z in zooms]
    pshape = tuple(s + 2 * mg for s, mg in zip(dmask.shape, marg))
    S = np.fft.rfftn(acf(_lag_mm(pshape, zooms))).real
    amp = np.sqrt(np.clip(S, 0, None))
    rng = np.random.default_rng(seed)
    crop = tuple(slice(mg, mg + s) for mg, s in zip(marg, dmask.shape))
    for _ in range(n):
        f = np.fft.irfftn(np.fft.rfftn(rng.standard_normal(pshape)) * amp, pshape)[crop]
        v = f[dmask]
        sd = v.std()
        yield (v - v.mean()) / sd if sd > 0 else np.zeros_like(v)


def max_cluster(v, dmask, st, z_thr=1.95):
    """Size of the largest cluster of |v| > z_thr, clustered separately for
    each sign with structuring element ``st``."""
    best = 0
    for sgn in (1, -1):
        vol = np.zeros(dmask.shape, bool)
        vol[dmask] = sgn * v > z_thr
        lab, n = ndimage.label(vol, structure=st)
        if n:
            best = max(best, int(np.bincount(lab.ravel())[1:].max()))
    return best


def mc_k(
    a,
    b,
    c,
    dmask,
    zooms,
    n=1000,
    z_thr=1.95,
    alpha=0.05,
    seed=0,
    connectivity=1,
    acf=None,
    acf_extent_mm=0.0,
):
    """Monte Carlo cluster-extent threshold: the smallest k such that the
    fraction of null fields whose largest cluster has >= k voxels is at most
    ``alpha``. Returns k and the median and 95th percentile of the null
    largest-cluster distribution."""
    st = ndimage.generate_binary_structure(3, connectivity)
    mx = np.array(
        [
            max_cluster(v, dmask, st, z_thr)
            for v in null_fields(
                a, b, c, dmask, zooms, n, seed, acf=acf, acf_extent_mm=acf_extent_mm
            )
        ]
    )
    k = next(k for k in range(1, mx.max() + 2) if np.mean(mx >= k) <= alpha)
    return int(k), {
        "max_cluster_median": float(np.median(mx)),
        "max_cluster_p95": float(np.percentile(mx, 95)),
    }


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class ClusterExtentMCInputSpec(BaseInterfaceInputSpec):
    residual_file = File(
        exists=True,
        mandatory=True,
        desc="4D residuals of the stage-2 dual regression, inside the mask",
    )
    mask_file = File(exists=True, mandatory=True, desc="3D mask of the residuals")
    z_thr = traits.Float(
        1.95, usedefault=True, desc="Two-sided |z| threshold of the null fields"
    )
    alpha = traits.Float(
        0.05,
        usedefault=True,
        desc="Tail probability of the null largest-cluster distribution",
    )
    n_sim = traits.Int(1000, usedefault=True, desc="Number of null fields")
    n_vol = traits.Int(
        60, usedefault=True, desc="Residual volumes used for the empirical ACF"
    )
    r_max_mm = traits.Float(
        30.0, usedefault=True, desc="Largest distance (mm) of the empirical ACF"
    )
    random_state = traits.Int(0, usedefault=True, desc="Seed of the null fields")
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the ACF fit and the null fields"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class ClusterExtentMCOutputSpec(TraitedSpec):
    min_cluster_voxels = traits.Int(desc="Cluster-extent threshold k (voxels)")
    report_file = File(desc="JSON report: ACF fit, null distribution, k")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class ClusterExtentMC(BaseInterface):
    """
    Monte Carlo cluster-extent threshold k for spatially z-scored IC maps,
    estimated from the spatial smoothness of the dual-regression residuals.

    1. Empirical spatial ACF of the residuals (each voxel scaled to unit
       temporal variance; mask-normalised FFT autocorrelation, 1 mm bins up to
       ``r_max_mm``; lags with 1000 voxel pairs or fewer are skipped).
    2. Least-squares fit of the mixed ACF of Cox et al. 2017, eq. 3,
       h(r) = a exp(-r^2 / (2 b^2)) + (1 - a) exp(-r / c), whose long tail
       addresses the cluster-inference failures of Gaussian-ACF models
       reported by Eklund et al. 2016.
    3. ``n_sim`` null Gaussian fields with that ACF on the subject grid and
       mask (Forman et al. 1995; Ward 2000), each spatially standardised
       within the mask like the IC maps, thresholded at |z| > ``z_thr`` and
       split into 6-connected clusters per sign; the largest cluster of each
       field is recorded.
    4. k = the smallest size with P(largest null cluster >= k) <= ``alpha``.

    Spatial z on IC maps is not an inferential statistic; k is a
    smoothness-derived extent, not a controlled false-positive rate.

    If the ACF cannot be fitted (``curve_fit`` fails, or the residuals have
    no measurable variance and only the lag-0 point exists), the null fields
    use the binned empirical ACF itself, linearly interpolated and 0 beyond
    the last bin; with no measurable correlation this is white noise. This
    fallback is a design choice (on synthetic residuals it gave a k about 6%
    below the fitted one). The report records ``acf_model`` ("fitted" or "empirical") and the fit error.

    Timing: 1000 null fields at about 65k voxels take about 10-30 s (about
    10 s measured at 69k voxels with 3 BLAS threads).

    References:
    - Forman SD, Cohen JD, Fitzgerald M, Eddy WF, Mintun MA, Noll DC (1995).
      Improved assessment of significant activation in functional magnetic
      resonance imaging (fMRI): use of a cluster-size threshold. Magn Reson
      Med 33:636-647. doi:10.1002/mrm.1910330508
    - Ward BD (2000). Simultaneous inference for fMRI data. AFNI AlphaSim
      documentation, Medical College of Wisconsin.
    - Cox RW, Chen G, Glen DR, Reynolds RC, Taylor PA (2017). FMRI clustering
      in AFNI: false-positive rates redux. Brain Connect 7(3):152-171, eq. 3.
      doi:10.1089/brain.2016.0475
    - Eklund A, Nichols TE, Knutsson H (2016). Cluster failure: why fMRI
      inferences for spatial extent have inflated false-positive rates.
      PNAS 113(28):7900-7905. doi:10.1073/pnas.1602413113
    - Wood ATA, Chan G (1994). Simulation of stationary Gaussian processes in
      [0,1]^d. J Comput Graph Stat 3(4):409-432.
      doi:10.1080/10618600.1994.10474655
    - Dietrich CR, Newsam GN (1997). Fast and exact simulation of stationary
      Gaussian processes through circulant embedding of the covariance
      matrix. SIAM J Sci Comput 18(4):1088-1107. doi:10.1137/S1064827592240555
    - Padfield D (2012). Masked object registration in the Fourier domain.
      IEEE Trans Image Process 21(5):2706-2718. doi:10.1109/TIP.2011.2181402
    """

    input_spec = ClusterExtentMCInputSpec
    output_spec = ClusterExtentMCOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        t0 = time.time()
        mask_img = nib.load(self.inputs.mask_file)
        dmask = np.asanyarray(mask_img.dataobj) > 0
        res_img = nib.load(self.inputs.residual_file)
        zooms = tuple(float(z) for z in res_img.header.get_zooms()[:3])
        R = np.asanyarray(res_img.dataobj)[dmask].astype(np.float64)
        if R.ndim == 1:
            R = R[:, None]

        rc, vc = empirical_acf(
            R, dmask, zooms, n_vol=self.inputs.n_vol, r_max_mm=self.inputs.r_max_mm
        )
        report = {"r_mm": rc.tolist(), "acf": vc.tolist()}
        acf, acf_extent_mm = None, 0.0
        try:
            (a, b, c), rmse = fit_acf(rc, vc)
            if not np.all(np.isfinite([a, b, c, rmse])):
                raise ValueError("non-finite ACF parameters")
            report.update(
                acf_model="fitted",
                a=a,
                b_mm=b,
                c_mm=c,
                fwhm_gauss_mm=float(FWHM_PER_B * b),
                rmse=rmse,
            )
        except (RuntimeError, ValueError, TypeError) as err:
            acf, acf_extent_mm = empirical_acf_function(rc, vc), float(rc[-1])
            a = b = c = float("nan")
            report.update(acf_model="empirical", fit_error=str(err))
            iflogger.warning(
                "ClusterExtentMC: ACF fit failed (%s); the null fields use the "
                "binned empirical ACF",
                err,
            )

        t1 = time.time()
        k, info = mc_k(
            a,
            b,
            c,
            dmask,
            zooms,
            n=self.inputs.n_sim,
            z_thr=self.inputs.z_thr,
            alpha=self.inputs.alpha,
            seed=self.inputs.random_state,
            acf=acf,
            acf_extent_mm=acf_extent_mm,
        )
        report.update(
            min_cluster_voxels=k,
            n_sim=self.inputs.n_sim,
            alpha=self.inputs.alpha,
            z_thr=self.inputs.z_thr,
            random_state=self.inputs.random_state,
            n_voxels=int(dmask.sum()),
            mc_wall_s=time.time() - t1,
            wall_s=time.time() - t0,
            **info,
        )

        self._min_cluster_voxels = k
        self._report_file = os.path.join(runtime.cwd, "cluster_extent_mc.json")
        with open(self._report_file, "w") as f:
            json.dump(report, f, indent=1)
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["min_cluster_voxels"] = self._min_cluster_voxels
        outputs["report_file"] = self._report_file
        return outputs
