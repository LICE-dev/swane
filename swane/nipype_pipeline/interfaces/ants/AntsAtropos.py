# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
import os
from os.path import abspath

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    OutputMultiPath,
    isdefined,
)

# antspyx is imported lazily inside _run_interface, as in AntsN4BiasFieldCorrection.

ITK_THREADS_VAR = "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class AntsAtroposInputSpec(BaseInterfaceInputSpec):
    in_file = File(exists=True, mandatory=True, desc="the input (skull-stripped) image")
    mask_file = File(exists=True, desc="brain mask; if unset, in_file > 0 is used")
    number_classes = traits.Int(
        3, usedefault=True, desc="number of tissue classes (K-means initialization)"
    )
    mrf_smoothing = traits.Float(
        0.0, usedefault=True, desc="MRF smoothing factor (beta); 0 disables MRF"
    )
    mrf_radius = traits.Int(
        1, usedefault=True, desc="isotropic MRF neighborhood radius"
    )
    iterations = traits.Int(
        10, usedefault=True, desc="maximum EM iterations (convergence threshold 0)"
    )
    num_threads = traits.Int(nohash=True, desc="number of ITK threads")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class AntsAtroposOutputSpec(TraitedSpec):
    partial_volume_files = OutputMultiPath(
        File(exists=True),
        desc="per-class posterior probability maps, ascending intensity order "
        "[CSF, GM, WM] (matches FSL FAST partial_volume_files)",
    )
    tissue_class_map = File(exists=True, desc="hard segmentation label image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class AntsAtropos(BaseInterface):
    """
    Finite-mixture tissue segmentation via antspyx ``ants.atropos``.

    K-means initialization with no priors, so classes are ordered by ascending
    mean intensity (CSF, GM, WM on a T1) -- the same ordering FSL FAST produces
    for its partial-volume files.

    """

    input_spec = AntsAtroposInputSpec
    output_spec = AntsAtroposOutputSpec

    def _init_string(self):
        return "Kmeans[%d]" % self.inputs.number_classes

    def _mrf_string(self):
        r = self.inputs.mrf_radius
        return "[%g,%dx%dx%d]" % (self.inputs.mrf_smoothing, r, r, r)

    def _convergence_string(self):
        return "[%d,0]" % self.inputs.iterations

    def _posterior_names(self):
        return [
            abspath("atropos_pve_%d.nii.gz" % k)
            for k in range(self.inputs.number_classes)
        ]

    def _seg_name(self):
        return abspath("atropos_seg.nii.gz")

    def _run_interface(self, runtime):
        import ants

        img = ants.image_read(self.inputs.in_file, pixeltype="float")

        if isdefined(self.inputs.mask_file):
            mask = ants.image_read(self.inputs.mask_file)
            mask = (mask > 0).clone("float")
            # geometry-coherence guard (same tolerance as AntsN4BiasFieldCorrection)
            max_tolerance = 0.1
            distance = np.linalg.norm(np.array(img.origin) - np.array(mask.origin))
            if distance > 0:
                if distance <= max_tolerance:
                    mask.set_origin(img.origin)
                    mask.set_spacing(img.spacing)
                    mask.set_direction(img.direction)
                else:
                    raise RuntimeError(
                        f"Image and Mask do not coincide! Origin distance: "
                        f"{distance:.4f} mm. Maximum allowed threshold is "
                        f"{max_tolerance} mm."
                    )
        else:
            mask = (img > 0).clone("float")

        previous_threads = os.environ.get(ITK_THREADS_VAR)
        if isdefined(self.inputs.num_threads):
            os.environ[ITK_THREADS_VAR] = str(self.inputs.num_threads)
        try:
            res = ants.atropos(
                a=img,
                x=mask,
                i=self._init_string(),
                m=self._mrf_string(),
                c=self._convergence_string(),
            )
        finally:
            if previous_threads is None:
                os.environ.pop(ITK_THREADS_VAR, None)
            else:
                os.environ[ITK_THREADS_VAR] = previous_threads

        probs = res["probabilityimages"]
        if len(probs) != self.inputs.number_classes:
            raise RuntimeError(
                f"expected {self.inputs.number_classes} probability images, "
                f"got {len(probs)}"
            )
        for prob, path in zip(probs, self._posterior_names()):
            ants.image_write(prob, path)
        ants.image_write(res["segmentation"], self._seg_name())

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["partial_volume_files"] = self._posterior_names()
        outputs["tissue_class_map"] = self._seg_name()
        return outputs
