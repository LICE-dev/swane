# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
import numpy as np
import pandas as pd
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
class NilearnFirstLevelInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="Preprocessed 4D EPI")
    mask_file = File(exists=True, mandatory=True, desc="Dilated 3D brain mask")
    tr = traits.Float(mandatory=True, desc="Repetition time")
    subject_info = traits.Any(mandatory=True, desc="Nipype Bunch from FMRIGenSpec")
    realignment_parameters = File(exists=True, mandatory=True, desc="6 motion params")
    outlier_files = traits.Either(
        File(exists=True),
        traits.List(File(exists=True)),
        desc="ArtifactDetect outlier files",
    )
    contrasts = traits.List(desc="List of contrast definitions")
    num_threads = traits.Int(
        nohash=True, desc="OpenMP/BLAS thread count for the GLM fit"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class NilearnFirstLevelOutputSpec(TraitedSpec):
    zstats = traits.List(File(exists=True), desc="Z-stat maps per contrast")
    threshold_file_cont1_thresh1 = File(desc="Contrast 1, thresh 3.1")
    threshold_file_cont1_thresh2 = File(desc="Contrast 1, thresh 5.0")
    threshold_file_cont1_thresh3 = File(desc="Contrast 1, thresh 7.0")
    threshold_file_cont2_thresh1 = File(desc="Contrast 2, thresh 3.1")
    threshold_file_cont2_thresh2 = File(desc="Contrast 2, thresh 5.0")
    threshold_file_cont2_thresh3 = File(desc="Contrast 2, thresh 7.0")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class NilearnFirstLevel(BaseInterface):
    """
    nilearn first-level GLM on the already-preprocessed 4D data.

    References:
    - Friston KJ, et al. (1994). Statistical parametric maps in functional imaging: a general linear approach.
      Hum Brain Mapp 2:189-210. doi:10.1002/hbm.460020402
    - Abraham A, et al. (2014). Machine learning for neuroimaging with scikit-learn.
      Front Neuroinform 8:14 (nilearn FirstLevelModel). doi:10.3389/fninf.2014.00014
    """

    input_spec = NilearnFirstLevelInputSpec
    output_spec = NilearnFirstLevelOutputSpec

    def _run_interface(self, runtime):
        num_threads = (
            int(self.inputs.num_threads) if isdefined(self.inputs.num_threads) else 1
        )
        with threadpool_limits(limits=num_threads):
            return self._run_numeric(runtime)

    def _run_numeric(self, runtime):
        from nilearn.glm.first_level import FirstLevelModel
        from nilearn.image import threshold_img

        in_file = self.inputs.in_file
        mask_file = self.inputs.mask_file
        tr = self.inputs.tr

        # Build events DataFrame from Nipype Bunch
        info = self.inputs.subject_info
        events_list = []
        for i, cond in enumerate(info.conditions):
            onsets_i = info.onsets[i]
            durations_i = info.durations[i]
            if len(durations_i) == 1 and len(onsets_i) > 1:
                durations_i = durations_i * len(onsets_i)
            for onset, duration in zip(onsets_i, durations_i):
                events_list.append(
                    {
                        "onset": onset,
                        "duration": duration,
                        "trial_type": cond.replace(" ", "_"),
                    }
                )
        events = pd.DataFrame(events_list)

        # Build confounds DataFrame
        params_spm = np.atleast_2d(np.loadtxt(self.inputs.realignment_parameters))
        n_vols = params_spm.shape[0]
        conf = pd.DataFrame(params_spm, columns=[f"mot{i:02d}" for i in range(6)])

        if self.inputs.outlier_files:
            outlier_file = self.inputs.outlier_files
            if isinstance(outlier_file, list):
                outlier_file = outlier_file[0]
            if os.path.getsize(outlier_file):
                outliers = np.loadtxt(outlier_file, dtype=int, ndmin=1)
                for k, vol in enumerate(outliers):
                    spike = np.zeros(n_vols)
                    if 0 <= int(vol) < n_vols:
                        spike[int(vol)] = 1.0
                    conf[f"spike{k:02d}"] = spike

        # nilearn FirstLevelModel
        flm = FirstLevelModel(
            t_r=tr,
            slice_time_ref=0.0,
            hrf_model="spm",  # canonical, no derivative
            drift_model=None,  # high-pass already applied via niimath
            high_pass=None,
            smoothing_fwhm=None,  # smoothing already applied
            mask_img=mask_file,
            noise_model="ar1",  # AR(1) noise model
            standardize=False,
            minimize_memory=False,
        )
        flm.fit(in_file, events=events, confounds=conf)

        self._zstats = []
        self._thresholds = {}

        for cont_idx, contrast_def in enumerate(self.inputs.contrasts):
            cont_name = contrast_def[0].replace(" ", "_")
            c_conds = contrast_def[2]
            c_weights = contrast_def[3]

            # Construct contrast expression (e.g. "TaskA - TaskB")
            cexpr = " + ".join(
                [f"({w}) * {c.replace(' ', '_')}" for w, c in zip(c_weights, c_conds)]
            )

            zmap = flm.compute_contrast(cexpr, output_type="z_score")
            zmap_path = os.path.join(runtime.cwd, f"z_{cont_name}.nii.gz")
            zmap.to_filename(zmap_path)
            self._zstats.append(zmap_path)

            for t_idx, z_val in enumerate([3.1, 5.0, 7.0]):
                thr = threshold_img(
                    zmap,
                    threshold=z_val,
                    cluster_threshold=10,
                    mask_img=mask_file,
                    two_sided=False,
                    copy=True,
                )
                thr_path = os.path.join(
                    runtime.cwd,
                    f"r-{cont_name}_cluster_{cont_name}_threshold{z_val:.1f}.nii.gz",
                )
                thr.to_filename(thr_path)
                self._thresholds[f"threshold_file_cont{cont_idx+1}_thresh{t_idx+1}"] = (
                    thr_path
                )

        return runtime

    def _list_outputs(self):
        outputs = self._outputs().get()
        outputs["zstats"] = self._zstats
        for key, val in self._thresholds.items():
            outputs[key] = val
        return outputs
