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
from threadpoolctl import threadpool_limits


def friston24(par_spm):
    """Friston et al. 1996 24-parameter motion model: R, R', R^2, R'^2 (R' is
    the backward temporal difference, first row 0), demeaned column-wise.
    par_spm: T x 6, SPM order [tx,ty,tz (mm), rx,ry,rz (rad)].

    References:
    - Friston KJ, et al. (1996). Movement-related effects in fMRI
      time-series. Magnetic Resonance in Medicine 35:346-355.
    """
    d = np.diff(par_spm, axis=0, prepend=par_spm[:1])
    X = np.hstack([par_spm, d, par_spm**2, d**2])
    return X - X.mean(axis=0)


def regress(Y_vt, X):
    """Residualise Y (V,T) on X (T,p) plus a constant column, OLS, keeping
    each voxel's temporal mean. Returns (Y_regressed, rank), rank including
    the constant column.

    References:
    - Pruim RHR, et al. (2015). ICA-AROMA. NeuroImage 112:267-277.
    - Pruim RHR, et al. (2015). NeuroImage 112:278-287 (Suppl.).
    """
    T = Y_vt.shape[1]
    Xf = np.hstack([np.ones((T, 1)), X]) if X.size else np.ones((T, 1))
    mu = Y_vt.mean(axis=1, keepdims=True)
    beta = np.linalg.pinv(Xf) @ Y_vt.T  # (p+1, V)
    res = Y_vt.T - Xf @ beta  # (T, V)
    rank = int(np.linalg.matrix_rank(Xf))
    return res.T + mu, rank, Xf


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class NuisanceRegressionInputSpec(BaseInterfaceInputSpec):
    in_file = File(
        exists=True,
        mandatory=True,
        desc="Smoothed 4D EPI; also sampled for the ROI regressors",
    )
    twin_file = File(
        exists=True,
        mandatory=True,
        desc="Unsmoothed twin 4D EPI, regressed with the same design",
    )
    mask_file = File(exists=True, mandatory=True, desc="Dilated 3D brain mask")
    wm_roi_file = File(exists=True, mandatory=True, desc="White-matter nuisance ROI")
    csf_roi_file = File(exists=True, mandatory=True, desc="CSF nuisance ROI")
    par_file = File(
        exists=True,
        desc="Realignment parameters, SPM order [tx,ty,tz (mm), rx,ry,rz (rad)] (required when motion24 is True)",
    )
    motion24 = traits.Bool(
        False,
        usedefault=True,
        desc="Add the Friston-24 motion regressors to the design",
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the regressions"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class NuisanceRegressionOutputSpec(TraitedSpec):
    out_file = File(desc="Nuisance-regressed smoothed 4D EPI, per-voxel mean restored")
    twin_out_file = File(
        desc="Twin 4D EPI regressed with the same design, per-voxel mean restored"
    )
    design_file = File(
        desc="Design matrix actually used (T x (p+1), constant column first), as text"
    )
    rank = traits.Int(desc="Matrix rank of the design including the constant column")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class NuisanceRegression(BaseInterface):
    """
    Nuisance regression: OLS residualisation of the smoothed data (and
    the same regression applied to the unsmoothed twin) on a design of
    linear trend, mean WM signal, mean CSF signal, and, when AROMA is not run
    upstream, the Friston-24 motion parameters. Regressors are sampled from
    the smoothed data inside the WM/CSF ROIs; the OLS includes a constant and
    each voxel's temporal mean is restored after residualisation.

    The twin is the input before spatial smoothing. Smoothing (linear in
    space) and this regression (linear in time, same design) commute, so the
    regressed twin is the regressed data before smoothing; it serves the
    model-order estimate, whose information criteria assume independent
    voxel samples (Li et al. 2007). Using an unsmoothed twin for this is a
    design choice of this interface.

    References:
    - Pruim RHR, et al. (2015). ICA-AROMA: A robust ICA-based strategy for
      removing motion artifacts from fMRI data. NeuroImage 112:267-277.
    - Pruim RHR, et al. (2015). Evaluation of ICA-AROMA and alternative
      strategies for motion artifact removal in resting state fMRI.
      NeuroImage 112:278-287.
    - Friston KJ, et al. (1996). Movement-related effects in fMRI
      time-series. Magnetic Resonance in Medicine 35:346-355.
    - Li Y-O, Adali T, Calhoun VD (2007). Estimating the number of
      independent components for functional magnetic resonance imaging data.
      Hum Brain Mapp 28:1251-1266.
    """

    input_spec = NuisanceRegressionInputSpec
    output_spec = NuisanceRegressionOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        out_dir = runtime.cwd

        mask_img = nib.load(self.inputs.mask_file)
        mask = mask_img.get_fdata() > 0
        wm_roi = nib.load(self.inputs.wm_roi_file).get_fdata() > 0
        csf_roi = nib.load(self.inputs.csf_roi_file).get_fdata() > 0

        if not np.any(wm_roi):
            raise ValueError(
                "NuisanceRegression: WM ROI is empty — the nuisance "
                "regression requires at least one WM voxel inside the mask."
            )
        if not np.any(csf_roi):
            raise ValueError(
                "NuisanceRegression: CSF ROI is empty — the nuisance "
                "regression requires at least one CSF voxel inside the mask."
            )

        in_img = nib.load(self.inputs.in_file)
        data = in_img.get_fdata()
        twin = nib.load(self.inputs.twin_file).get_fdata()

        T = data.shape[-1]
        trend = np.linspace(-1, 1, T)
        wm_ts = data[wm_roi].mean(axis=0)
        csf_ts = data[csf_roi].mean(axis=0)
        X = np.column_stack([trend, wm_ts, csf_ts])

        if self.inputs.motion24:
            if not isdefined(self.inputs.par_file):
                raise ValueError("NuisanceRegression: motion24=True requires par_file")
            par = np.loadtxt(self.inputs.par_file, ndmin=2)
            if par.shape[1] != 6:
                raise ValueError(
                    f"par_file: expected 6 columns (SPM order), got {par.shape[1]}"
                )
            X = np.hstack([X, friston24(par)])

        data_masked = data[mask]  # (V, T)
        twin_masked = twin[mask]

        out_masked, rank, Xf = regress(data_masked, X)
        twin_out_masked, _, _ = regress(twin_masked, X)

        out_vol = np.zeros(data.shape, dtype=np.float32)
        out_vol[mask] = out_masked.astype(np.float32)
        out_path = os.path.join(out_dir, "nuisance_regressed.nii.gz")
        out_img = nib.Nifti1Image(out_vol, in_img.affine)
        out_img.set_data_dtype(np.float32)
        nib.save(out_img, out_path)
        self._out_file = out_path

        twin_out_vol = np.zeros(twin.shape, dtype=np.float32)
        twin_out_vol[mask] = twin_out_masked.astype(np.float32)
        twin_out_path = os.path.join(out_dir, "nuisance_regressed_twin.nii.gz")
        twin_out_img = nib.Nifti1Image(twin_out_vol, in_img.affine)
        twin_out_img.set_data_dtype(np.float32)
        nib.save(twin_out_img, twin_out_path)
        self._twin_out_file = twin_out_path

        design_path = os.path.join(out_dir, "nuisance_design.txt")
        np.savetxt(design_path, Xf)
        self._design_file = design_path

        self._rank = rank

        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["out_file"] = self._out_file
        outputs["twin_out_file"] = self._twin_out_file
        outputs["design_file"] = self._design_file
        outputs["rank"] = self._rank
        return outputs
