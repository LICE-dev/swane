# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
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


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class NilearnCanICAInputSpec(BaseInterfaceInputSpec):
    preproc_file = File(exists=True, mandatory=True, desc="Preprocessed 4D EPI")
    mask_file = File(exists=True, mandatory=True, desc="Dilated 3D brain mask")
    n_components = traits.Int(mandatory=True, desc="Number of components")
    random_state = traits.Int(0, usedefault=True, desc="Random state for determinism")
    num_threads = traits.Int(
        nohash=True,
        desc="OpenMP/BLAS thread count for CanICA (its restarts run in-process)",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class NilearnCanICAOutputSpec(TraitedSpec):
    components_file = File(desc="CanICA spatial components")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class NilearnCanICA(BaseInterface):
    """
    nilearn CanICA on the fully preprocessed 4D data.

    The estimator combines a canonical correlation analysis based dimension
    reduction with FastICA restarts; here it is applied to a single 4D image.

    References:
    - Varoquaux G, et al. (2010). A group model for stable multi-subject ICA on fMRI datasets.
      NeuroImage 51(1):288-299. doi:10.1016/j.neuroimage.2010.02.010
    - Hyvärinen A, Oja E (2000). Independent component analysis: algorithms and applications.
      Neural Networks 13(4-5):411-430. doi:10.1016/S0893-6080(00)00026-5

    The OpenMP/BLAS pools are capped at ``num_threads`` (1 when undefined,
    as Nipype reserves for the node); the restarts run in one process.
    """

    input_spec = NilearnCanICAInputSpec
    output_spec = NilearnCanICAOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        from nilearn.decomposition import CanICA

        preproc_path = self.inputs.preproc_file
        mask_path = self.inputs.mask_file
        n_components = self.inputs.n_components
        random_state = self.inputs.random_state

        est = CanICA(
            n_components=n_components,
            mask=mask_path,
            random_state=random_state,
            standardize=True,
            detrend=False,
            high_pass=None,
            smoothing_fwhm=None,
            threshold=None,
            verbose=0,
            # One process: the restarts share the BLAS pool capped at
            # num_threads instead of multiplying it by the number of jobs.
            n_jobs=1,
        )
        est.fit(preproc_path)
        comp_img = est.components_img_

        out_file = os.path.join(runtime.cwd, "ica_IC.nii.gz")
        comp_img.to_filename(out_file)

        self._components_file = out_file
        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["components_file"] = self._components_file
        return outputs
