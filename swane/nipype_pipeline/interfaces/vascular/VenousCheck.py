# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from os.path import abspath
import nibabel as nib
import numpy as np
from swane.config.config_enums import VeinDetectionMode
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    InputMultiObject,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class VenousCheckInputSpec(BaseInterfaceInputSpec):
    in_files = InputMultiObject(File(exists=True), desc="List of splitted file")
    detection_mode = traits.Enum(VeinDetectionMode, usedefault=True)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class VenousCheckOutputSpec(TraitedSpec):
    out_file_veins = File(exists=True, desc="the output venous image")
    out_file_anat = File(exists=True, desc="the output anatomic image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class VenousCheck(BaseInterface):
    """
    Recognises the venous phase from the anatomic image of a phase contrast sequence based criteria specified by user.

    """

    input_spec = VenousCheckInputSpec
    output_spec = VenousCheckOutputSpec

    def _run_interface(self, runtime):
        # select which volume is venous and which is anatomic, without copying:
        # the outputs point to the original input files (nipype pass-through)
        if self.inputs.detection_mode == VeinDetectionMode.FIRST:
            self._veins, self._anat = 0, 1
        elif self.inputs.detection_mode == VeinDetectionMode.SECOND:
            self._veins, self._anat = 1, 0
        else:
            stats = []
            for f in self.inputs.in_files[:2]:
                data = nib.load(f).get_fdata(dtype=np.float32)
                if self.inputs.detection_mode == VeinDetectionMode.MEAN:
                    # mean of the non-zero voxels
                    stats.append(float(data[data != 0].mean()))
                elif self.inputs.detection_mode == VeinDetectionMode.KURTOSIS:
                    # excess kurtosis of the non-zero voxels: the venous
                    # (angiographic) phase suppresses the background and leaves a
                    # sparse, heavy-tailed intensity distribution, so it is far
                    # more leptokurtic than the anatomic magnitude phase
                    stats.append(self._excess_kurtosis(data[data != 0]))
                else:
                    # sample std (ddof=1) of all voxels
                    stats.append(float(data.std(ddof=1)))
            if self.inputs.detection_mode == VeinDetectionMode.KURTOSIS:
                # the venous phase is the one with the HIGHER kurtosis
                veins_is_first = stats[0] > stats[1]
            else:
                # the darker (lower statistic) volume is the venous one
                veins_is_first = stats[0] < stats[1]
            if veins_is_first:
                self._veins, self._anat = 0, 1
            else:
                self._veins, self._anat = 1, 0

        return runtime

    @staticmethod
    def _excess_kurtosis(values) -> float:
        """
        Fisher's excess kurtosis (m4 / m2**2 - 3) of a 1D array, matching the
        default (population moments) of ``scipy.stats.kurtosis`` without adding a
        runtime dependency on SciPy.
        """
        x = values.astype(np.float64)
        deviations = x - x.mean()
        m2 = np.mean(deviations**2)
        m4 = np.mean(deviations**4)
        if m2 == 0:
            return 0.0
        return float(m4 / (m2**2) - 3.0)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["out_file_veins"] = abspath(self.inputs.in_files[self._veins])
        outputs["out_file_anat"] = abspath(self.inputs.in_files[self._anat])
        return outputs
