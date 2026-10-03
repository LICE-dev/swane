# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
import numpy as np
import nibabel as nib
from scipy import stats
from scipy.special import betaln, ndtri_exp
from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    traits,
    isdefined,
)
from threadpoolctl import threadpool_limits

# Log of the smallest normal double: below it the survival function returned
# by scipy is subnormal or zero and its logarithm loses accuracy.
LOGP_NORMAL = float(np.log(np.finfo(float).tiny))


def _t_logsf_series(a, dof, max_terms=100000):
    """Log survival function of Student's t at a > 0, from
    sf = I_x(dof/2, 1/2) / 2 with x = dof / (dof + a^2) and the hypergeometric
    series of the incomplete beta function (DLMF 8.17.8),
    B_x(p, q) = x^p (1 - x)^q / p * F(p + q, 1; p + 1; x),
    summed in log space. The series converges geometrically with ratio of
    about x; it is used where the tail probability is below the normal
    double range, where x is well below 1 except for very large dof."""
    a = np.asarray(a, dtype=float)
    p, q = dof / 2.0, 0.5
    log_den = np.logaddexp(np.log(dof), 2.0 * np.log(a))  # log(dof + a^2)
    log_x = np.log(dof) - log_den
    log_1mx = 2.0 * np.log(a) - log_den
    x = np.exp(log_x)
    total = np.ones_like(a)
    term = np.ones_like(a)
    active = np.ones(a.shape, bool)
    n = 0
    while active.any() and n < max_terms:
        term[active] *= (p + q + n) / (p + 1 + n) * x[active]
        total[active] += term[active]
        active &= term > 1e-17 * total
        n += 1
    log_i = p * log_x + q * log_1mx - np.log(p) - betaln(p, q) + np.log(total)
    return np.log(0.5) + log_i


def _t_logsf(a, dof):
    """Log survival function of Student's t at a >= 0: scipy where the tail
    probability is a normal double, the incomplete-beta series elsewhere."""
    logp = np.asarray(stats.t.logsf(a, dof), dtype=float)
    low = ~(logp > LOGP_NORMAL)
    if np.any(low):
        logp[low] = _t_logsf_series(a[low], dof)
    return logp


def t_to_z(t, dof):
    """Convert Student-t statistics to Gaussian z with the same tail
    probability (probability integral transform), sign-symmetric.

    Both steps work in log space, so no tail probability underflows: the
    log survival function of t (``_t_logsf``) is mapped to z with
    ``scipy.special.ndtri_exp``, the inverse of the log normal CDF.

    References:
    - NIST Digital Library of Mathematical Functions, eq. 8.17.8
      (hypergeometric representation of the incomplete beta function),
      https://dlmf.nist.gov/8.17
    """
    t = np.asarray(t, dtype=float)
    return np.sign(t) * -ndtri_exp(_t_logsf(np.abs(t), dof))


def dual_regression_zstat(data_vt, maps_vk, dof=None, centre_maps=True, to_z=True):
    """Dual regression (Filippini et al. 2009).

    Stage 1 regresses the component maps (spatially centred when
    ``centre_maps``) on every volume to get one time course per component;
    stage 2 regresses those time courses, plus an intercept, on every voxel.
    The OLS t = beta/SE uses the residual dof ``eff = dof - (K+1)`` (floor 1),
    where ``dof`` defaults to T (the number of timepoints) and can be lowered
    by the caller to account for degrees of freedom already removed upstream
    (e.g. nuisance regression, high-pass basis and denoised motion
    components). With ``to_z`` the t values are mapped to Gaussian z with
    ``eff`` degrees of freedom (``t_to_z``); otherwise the raw t is returned.

    Returns the maps (V,K), the stage-1 time courses (T,K) and the stage-2
    residuals (V,T), orthogonal to the stage-2 design by construction.

    References:
    - Filippini N, et al. (2009). Distinct patterns of brain activity in young
      carriers of the APOE-e4 allele. PNAS 106:7209-7214.
    - Beckmann CF, Mackay CE, Filippini N, Smith SM (2009). Group comparison
      of resting-state FMRI data using multi-subject ICA and dual regression.
      NeuroImage 47(Suppl 1):S148.
    - Nickerson LD, Smith SM, Ongur D, Beckmann CF (2017). Using dual
      regression to investigate network shape and amplitude in functional
      connectivity analyses. Front Neurosci 11:115 (mean-centred predictors).
    """
    V, T = data_vt.shape
    K = maps_vk.shape[1]
    Yt = data_vt.T  # (T, V)
    Yt = Yt - Yt.mean(axis=0, keepdims=True)  # demean over time

    if centre_maps:
        maps_vk = maps_vk - maps_vk.mean(axis=0, keepdims=True)
    Tc = Yt @ np.linalg.pinv(maps_vk.T)  # stage 1 -> (T, K)
    Tc_ext = np.hstack([Tc, np.ones((T, 1))])  # + intercept -> (T, K+1)

    beta_ext = np.linalg.pinv(Tc_ext) @ Yt  # stage 2 -> (K+1, V)
    res = Yt - Tc_ext @ beta_ext
    eff = max((T if dof is None else dof) - (K + 1), 1)
    var_res = np.sum(res**2, axis=0) / eff
    inv = np.linalg.inv(Tc_ext.T @ Tc_ext)
    se = np.sqrt(np.outer(np.diag(inv)[:-1], var_res))  # (K, V)
    # se is 0 only where the residual variance is 0 (constant voxel, beta 0).
    se[se == 0] = 1e-10
    z = beta_ext[:-1, :] / se  # (K, V)
    if to_z:
        z = t_to_z(z, eff)
    return z.T, Tc, res.T  # (V, K), (T, K), (V, T)


def component_power_spectra(time_series):
    x = time_series - time_series.mean(axis=0, keepdims=True)
    power = np.abs(np.fft.rfft(x, axis=0)) ** 2
    return power[1:]


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DualRegressionZStatInputSpec(BaseInterfaceInputSpec):
    preproc_file = File(exists=True, mandatory=True, desc="Preprocessed 4D EPI")
    mask_file = File(exists=True, mandatory=True, desc="Dilated 3D brain mask")
    components_file = File(
        exists=True, mandatory=True, desc="Spatial component maps (4D)"
    )
    dof = traits.Int(
        desc="Degrees of freedom of the data before the (K+1) stage-2 "
        "regressors are subtracted: T minus the degrees of freedom already "
        "removed upstream, e.g. nuisance regression, high-pass basis and "
        "denoised motion components. Defaults to T (the number of timepoints) "
        "when omitted."
    )
    centre_maps = traits.Bool(
        True,
        usedefault=True,
        desc="Spatially centre the component maps before stage 1",
    )
    t_to_z = traits.Bool(
        True,
        usedefault=True,
        desc="Convert the stage-2 t statistics to Gaussian z; if False the "
        "raw t is written",
    )
    write_residuals = traits.Bool(
        True,
        usedefault=True,
        desc="Write the stage-2 residuals as a 4D file (residual_file); "
        "disable when nothing consumes them",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the two regressions"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DualRegressionZStatOutputSpec(TraitedSpec):
    zstat_file = File(desc="Dual-regression z-maps")
    ic_mix = File(desc="Component time series (stage 1)")
    ic_ft_mix = File(desc="Component power spectra (DC-dropped)")
    residual_file = File(
        desc="Masked stage-2 residuals (4D), orthogonal to the stage-1 time courses"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DualRegressionZStat(BaseInterface):
    """
    Dual regression -> per-component z-statistics, time series, power spectra
    and stage-2 residuals.

    Stage-1 regressors are the component maps, spatially centred unless
    ``centre_maps`` is False. The stage-2 t statistics use the residual
    degrees of freedom ``dof - (K+1)`` (``dof`` defaults to T) and are mapped
    to Gaussian z by the probability integral transform (Student-t ->
    standard normal quantile) unless ``t_to_z`` is False. When
    ``dof - (K+1)`` is below 1 there is no residual degree of freedom for the
    statistics and the node stops with an error. The component time
    courses are written as ``ica_mix`` and their periodogram (the squared
    magnitude of their discrete Fourier transform, DC dropped) as
    ``ica_FTmix``, the format consumed by the ICA-AROMA frequency features
    (Pruim et al. 2015).

    References:
    - Filippini N, et al. (2009). Distinct patterns of brain activity in young carriers
      of the APOE-e4 allele. PNAS 106:7209-7214.
    - Beckmann CF, Mackay CE, Filippini N, Smith SM (2009). Group comparison
      of resting-state FMRI data using multi-subject ICA and dual regression.
      NeuroImage 47(Suppl 1):S148.
    - Nickerson LD, Smith SM, Ongur D, Beckmann CF (2017). Using dual
      regression to investigate network shape and amplitude in functional
      connectivity analyses. Front Neurosci 11:115.
    - Pruim RHR, et al. (2015). ICA-AROMA: A robust ICA-based strategy for
      removing motion artifacts from fMRI data. NeuroImage 112:267-277.
    """

    input_spec = DualRegressionZStatInputSpec
    output_spec = DualRegressionZStatOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        preproc_path = self.inputs.preproc_file
        mask_path = self.inputs.mask_file
        components_path = self.inputs.components_file
        dof = self.inputs.dof if isdefined(self.inputs.dof) else None
        out_dir = runtime.cwd

        mask_img = nib.load(mask_path)
        mask_data = mask_img.get_fdata() > 0
        Y = nib.load(preproc_path).get_fdata()[mask_data]
        maps = nib.load(components_path).get_fdata()[mask_data]

        T, K = Y.shape[1], maps.shape[1]
        if (T if dof is None else dof) - (K + 1) < 1:
            raise ValueError(
                "DualRegressionZStat: no residual degrees of freedom for the "
                "stage-2 statistics (T=%d, dof=%s, %d components + intercept). "
                "The run has too few volumes for the degrees of freedom removed "
                "upstream and the number of components."
                % (T, "T" if dof is None else dof, K)
            )

        z_masked, Tc, res_masked = dual_regression_zstat(
            Y,
            maps,
            dof=dof,
            centre_maps=self.inputs.centre_maps,
            to_z=self.inputs.t_to_z,
        )

        K = z_masked.shape[1]
        z_vol = np.zeros(mask_img.shape + (K,))
        z_vol[mask_data] = z_masked

        z_path = os.path.join(out_dir, "zstat.nii.gz")
        nib.save(nib.Nifti1Image(z_vol, mask_img.affine, mask_img.header), z_path)
        self._zstat_file = z_path

        ic_mix_path = os.path.join(out_dir, "ica_mix")
        np.savetxt(ic_mix_path, Tc)
        self._ic_mix = ic_mix_path

        power_spectra = component_power_spectra(Tc)
        ic_ft_mix_path = os.path.join(out_dir, "ica_FTmix")
        np.savetxt(ic_ft_mix_path, power_spectra)
        self._ic_ft_mix = ic_ft_mix_path

        self._residual_file = None
        if not self.inputs.write_residuals:
            return runtime

        res_vol = np.zeros(mask_img.shape + (Y.shape[1],), dtype=np.float32)
        res_vol[mask_data] = res_masked.astype(np.float32)
        res_path = os.path.join(out_dir, "dr_residuals.nii.gz")
        res_img = nib.Nifti1Image(res_vol, mask_img.affine)
        res_img.set_data_dtype(np.float32)
        nib.save(res_img, res_path)
        self._residual_file = res_path

        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["zstat_file"] = self._zstat_file
        outputs["ic_mix"] = self._ic_mix
        outputs["ic_ft_mix"] = self._ic_ft_mix
        if self._residual_file is not None:
            outputs["residual_file"] = self._residual_file
        return outputs
