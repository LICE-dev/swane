# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

import shutil

import nibabel as nib
from nipype.interfaces.base import isdefined
from nipype.interfaces.fsl.utils import FilterRegressor


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.utils.FilterRegressor)  -*-
class CustomFilterRegressor(FilterRegressor):
    """
    Data de-noising by regressing out part of a design matrix, tolerating an
    empty list of components.

    ``fsl_regfilt`` fails on an empty ``filter_columns`` (``-f ''``). When the
    list is empty there is nothing to regress out, so the input image is passed
    through unchanged to ``out_file`` and ``fsl_regfilt`` does not run, as
    ICA-AROMA does when it flags no motion component. This is the only
    difference from the Nipype interface: ``mask``, ``var_norm`` and
    ``out_vnscales`` have no effect on that pass-through (SWANe sets none of
    them).

    """

    def _run_interface(self, runtime):
        if isdefined(self.inputs.filter_columns) and not self.inputs.filter_columns:
            return self._pass_through(runtime)
        return super()._run_interface(runtime)

    def _pass_through(self, runtime):
        in_file = self.inputs.in_file
        out_file = self._list_outputs()["out_file"]
        if in_file.endswith(".gz") == out_file.endswith(".gz"):
            shutil.copyfile(in_file, out_file)
        else:
            # Copying would leave gzip data under a plain .nii name (or the
            # reverse): let nibabel write the requested format.
            nib.save(nib.load(in_file), out_file)
        runtime.returncode = 0
        runtime.stdout = (
            "No component to filter out: fsl_regfilt not run, input copied to %s"
            % out_file
        )
        runtime.stderr = ""
        return runtime
