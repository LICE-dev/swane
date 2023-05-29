# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import (traits, TraitedSpec, BaseInterface, BaseInterfaceInputSpec)
from scipy.stats import ttest_ind_from_stats


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class TTestInputSpec(BaseInterfaceInputSpec):
    stats_lh = traits.List(mandatory=True, desc='Stats for left side')
    stats_rh = traits.List(mandatory=True, desc='Stats for right side')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class TTestOutputSpec(TraitedSpec):
    stat_t = traits.Float(desc="T statistics")
    stat_p = traits.Float(desc="P value")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class TTest(BaseInterface):
    """
    Reads the num. of volumes from a 4d NIFTI file.

    """

    input_spec = TTestInputSpec
    output_spec = TTestOutputSpec

    def _run_interface(self, runtime):
        try:
            self.t, self.p = ttest_ind_from_stats(mean1=self.inputs.stats_lh[0], std1=self.inputs.stats_lh[1], nobs1=self.inputs.stats_lh[2], mean2=self.inputs.stats_rh[0], std2=self.inputs.stats_rh[1], nobs2=self.inputs.stats_rh[2])
        except:
            self.t = 0
            self.p = 0

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['stat_t'] = self.t
        outputs['stat_p'] = self.p
        return outputs
