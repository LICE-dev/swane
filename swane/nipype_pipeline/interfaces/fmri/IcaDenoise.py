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
from nilearn import signal


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class IcaDenoiseInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="Native 4D EPI (intnorm)")
    mask_file = File(exists=True, mandatory=True, desc="Brain mask")
    ic_mix = File(exists=True, mandatory=True, desc="Component time series")
    motion_ics = traits.Either(
        traits.List(traits.Int),
        traits.Str,
        File(exists=True),
        mandatory=True,
        desc="Indices of noise components, 1-based",
    )
    aggressive = traits.Bool(
        False, usedefault=True, desc="Use aggressive (full) regression"
    )
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the component regression"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class IcaDenoiseOutputSpec(TraitedSpec):
    denoised_file = File(desc="Denoised 4D EPI")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class IcaDenoise(BaseInterface):
    """
    Produce the ICA-AROMA denoised 4D outputs by least-squares regression.

    Aggressive mode regresses the selected noise component time courses out of
    the data (via nilearn.signal.clean); non-aggressive mode fits all component
    time courses jointly and removes only the contribution of the selected
    ones (unique variance). The voxel-wise mean is restored in both modes.

    References:
    - Pruim RHR, et al. (2015). ICA-AROMA: A robust ICA-based strategy for
      removing motion artifacts from fMRI data. NeuroImage 112:267-277.
      doi:10.1016/j.neuroimage.2015.02.064
    - Griffanti L, et al. (2014). ICA-based artefact removal and accelerated
      fMRI acquisition for improved resting state network imaging.
      NeuroImage 95:232-247 (aggressive vs. unique-variance noise removal).
      doi:10.1016/j.neuroimage.2014.03.034
    - Friston KJ, et al. (1994). Statistical parametric maps in functional
      imaging: a general linear approach. Hum Brain Mapp 2:189-210 (general
      linear model). doi:10.1002/hbm.460020402
    - Abraham A, et al. (2014). Machine learning for neuroimaging with
      scikit-learn. Front Neuroinform 8:14 (nilearn).
      doi:10.3389/fninf.2014.00014
    """

    input_spec = IcaDenoiseInputSpec
    output_spec = IcaDenoiseOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        func_path = self.inputs.in_file
        mask_path = self.inputs.mask_file
        ic_mix_path = self.inputs.ic_mix
        motion_ics_in = self.inputs.motion_ics
        aggressive = self.inputs.aggressive
        out_dir = runtime.cwd

        # Parse motion_ics
        if isinstance(motion_ics_in, list):
            # AromaClassification provides ICA-AROMA component numbers (1-based).
            motion_ics = [int(x) - 1 for x in motion_ics_in]
        elif isinstance(motion_ics_in, str) and os.path.isfile(motion_ics_in):
            with open(motion_ics_in, "r") as f:
                content = f.read().strip()
            if content:
                vals = content.replace(",", " ").split()
                # AROMA files use 1-based
                motion_ics = [int(x) - 1 for x in vals if x]
            else:
                motion_ics = []
        else:
            motion_ics = []

        func_img = nib.load(func_path)
        func_data = func_img.get_fdata()
        mask_img = nib.load(mask_path)
        mask_data = mask_img.get_fdata() > 0

        X = np.loadtxt(ic_mix_path)  # (T, K)
        if len(motion_ics) == 0:
            # no noise components
            out_name = (
                "denoised_func_data_aggr.nii.gz"
                if aggressive
                else "denoised_func_data_nonaggr.nii.gz"
            )
            out_file = os.path.join(out_dir, out_name)
            func_img.to_filename(out_file)
            self._denoised_file = out_file
            return runtime

        Y = func_data[mask_data].T  # (T, V)
        Y_mean = Y.mean(axis=0, keepdims=True)
        Y_dm = Y - Y_mean
        X_dm = X - X.mean(axis=0, keepdims=True)

        if aggressive:
            cleaned = signal.clean(
                Y_dm,
                confounds=X_dm[:, motion_ics],
                detrend=False,
                standardize=False,
                standardize_confounds=True,
            )
            Y_clean = cleaned - cleaned.mean(axis=0, keepdims=True) + Y_mean
            out_name = "denoised_func_data_aggr.nii.gz"
        else:
            beta = np.linalg.pinv(X_dm) @ Y_dm
            Y_clean = Y_dm - (X_dm[:, motion_ics] @ beta[motion_ics, :])
            Y_clean += Y_mean
            out_name = "denoised_func_data_nonaggr.nii.gz"

        out_data = func_data.copy()
        out_data[mask_data] = Y_clean.T
        out_img = nib.Nifti1Image(out_data, func_img.affine, header=func_img.header)
        out_file = os.path.join(out_dir, out_name)
        nib.save(out_img, out_file)

        self._denoised_file = out_file
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["denoised_file"] = self._denoised_file
        return outputs
