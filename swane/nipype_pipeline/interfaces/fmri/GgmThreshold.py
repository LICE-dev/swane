# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
import numpy as np
import nibabel as nib
from scipy.stats import norm, gamma
from sklearn.mixture import GaussianMixture
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)
from threadpoolctl import threadpool_limits


def _fit_gamma_moments(x, w):
    """Method-of-moments Gamma fit (fast, robust vs full ML; disclosed choice)."""
    ws = np.sum(w)
    if ws < 1e-6:
        return 1.0, 1.0
    m = np.sum(w * x) / ws
    if m <= 1e-6:
        return 1.0, 1.0
    v = np.sum(w * (x - m) ** 2) / ws
    if v <= 1e-6:
        return 1.0, 1.0
    scale = v / m
    return m / scale, scale


def ggm_posterior(z, max_iter=200, tol=1e-4):
    """Return the posterior probability of activation (pos or neg Gamma) per voxel."""
    V = len(z)
    zc = z.reshape(-1, 1)
    try:  # initialise from a 3-Gaussian fit: neg / noise / pos by mean order
        gmm = GaussianMixture(n_components=3, random_state=42, n_init=1).fit(zc)
        order = np.argsort(gmm.means_.flatten())
        neg_i, noise_i, pos_i = order
        resp = gmm.predict_proba(zc)
        r_neg, r_noise, r_pos = resp[:, neg_i], resp[:, noise_i], resp[:, pos_i]
        pi_noise, pi_pos, pi_neg = gmm.weights_[[noise_i, pos_i, neg_i]]
        mu_noise = gmm.means_.flatten()[noise_i]
        var_noise = gmm.covariances_[noise_i].flatten()[0]
    except Exception:  # degenerate component (pure noise): everything is null
        return np.zeros(V)

    a_pos = a_neg = 2.0
    s_pos = s_neg = 1.0
    prev = -np.inf
    evidence = np.ones(V)
    for _ in range(max_iter):
        # M-step: noise Gaussian, then Gammas on the tails beyond the noise mean
        wn = np.sum(r_noise)
        if wn > 1e-6:
            mu_noise = np.sum(r_noise * z) / wn
            var_noise = max(np.sum(r_noise * (z - mu_noise) ** 2) / wn, 1e-6)
        pos_m = z > mu_noise
        if np.any(pos_m):
            a_pos, s_pos = _fit_gamma_moments((z - mu_noise)[pos_m], r_pos[pos_m])
        neg_m = z < mu_noise
        if np.any(neg_m):
            a_neg, s_neg = _fit_gamma_moments(-(z - mu_noise)[neg_m], r_neg[neg_m])
        pi_noise, pi_pos, pi_neg = np.mean(r_noise), np.mean(r_pos), np.mean(r_neg)

        # E-step
        p_noise = norm.pdf(z, mu_noise, np.sqrt(var_noise))
        p_pos = np.zeros(V)
        p_neg = np.zeros(V)
        if pi_pos > 1e-4:
            p_pos[pos_m] = gamma.pdf(z[pos_m] - mu_noise, a=a_pos, scale=s_pos)
        if pi_neg > 1e-4:
            p_neg[neg_m] = gamma.pdf(-(z[neg_m] - mu_noise), a=a_neg, scale=s_neg)
        evidence = np.maximum(
            pi_noise * p_noise + pi_pos * p_pos + pi_neg * p_neg, 1e-15
        )
        r_noise = pi_noise * p_noise / evidence
        r_pos = pi_pos * p_pos / evidence
        r_neg = pi_neg * p_neg / evidence

        ll = np.sum(np.log(evidence))
        if abs(ll - prev) < tol:
            break
        prev = ll
    return (pi_pos * p_pos + pi_neg * p_neg) / evidence


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class GgmThresholdInputSpec(BaseInterfaceInputSpec):
    zstat_file = File(exists=True, mandatory=True, desc="Z-statistic 4D image")
    mask_file = File(exists=True, mandatory=True, desc="Brain mask")
    mm_thresh = traits.Float(0.5, usedefault=True, desc="Mixture model threshold")
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the mixture-model fits"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class GgmThresholdOutputSpec(TraitedSpec):
    thresh_zstat_files = traits.List(File(), desc="Thresholded Z-statistic 3D images")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class GgmThreshold(BaseInterface):
    """
    Gaussian/Gamma/Gamma mixture posterior thresholding.

    Per map, the in-mask Z values are modelled as a Gaussian null plus a Gamma
    tail on each side, fitted by EM (initialised from a 3-component Gaussian
    mixture, Gamma parameters by weighted method of moments); voxels whose
    posterior probability of belonging to a Gamma tail exceeds ``mm_thresh``
    keep their Z value. This is an adaptation of the alternative-hypothesis
    mixture-model inference of the reference, not a reimplementation of it.

    References:
    - Beckmann CF, Smith SM (2004). Probabilistic Independent Component Analysis
      for Functional Magnetic Resonance Imaging. IEEE TMI 23(2):137-152.
      doi:10.1109/TMI.2003.822821
    """

    input_spec = GgmThresholdInputSpec
    output_spec = GgmThresholdOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        zstat_path = self.inputs.zstat_file
        mask_path = self.inputs.mask_file
        mm_thresh = self.inputs.mm_thresh
        out_dir = runtime.cwd

        z_img = nib.load(zstat_path)
        z_data = z_img.get_fdata()
        mask_img = nib.load(mask_path)
        mask_data = mask_img.get_fdata() > 0

        K = z_data.shape[-1]
        z_masked = z_data[mask_data]  # (V, K)

        t_files = []
        for k in range(K):
            thr_masked = np.zeros_like(z_masked[:, k])
            post = ggm_posterior(z_masked[:, k])
            active = post > mm_thresh
            thr_masked[active] = z_masked[active, k]

            t_vol = np.zeros(z_img.shape[:-1])
            t_vol[mask_data] = thr_masked

            t_path = os.path.join(out_dir, f"thresh_zstat{k+1:02d}.nii.gz")
            nib.save(nib.Nifti1Image(t_vol, z_img.affine, z_img.header), t_path)
            t_files.append(t_path)

        self._thresh_zstat_files = t_files
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["thresh_zstat_files"] = self._thresh_zstat_files
        return outputs
