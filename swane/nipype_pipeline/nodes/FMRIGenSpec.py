# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import (traits, BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File, Bunch, isdefined)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class FMRIGenSpecInputSpec(BaseInterfaceInputSpec):
    TR = traits.Float(mandatory=True, desc="Repetition Time")
    nvols = traits.Int(mandatory=True, desc="Number of EPI runs")
    task_duration = traits.Int(mandatory=True, desc="Task duration")
    rest_duration = traits.Int(mandatory=True, desc="Rest duration")
    design_block = traits.Enum(0, 1, usedefault=True)
    task_a_name = traits.String(mandatory=False, desc="Task A name")
    task_b_name = traits.String(mandatory=False, desc="Task A name")
    hpcutoff = traits.Int(mandatory=False, desc="Cutoff for highpass filtering")
    tempMean = File(exists=True, mandatory=True, desc="mean functional image")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class FMRIGenSpecOutputSpec(TraitedSpec):
    hpcutoff = traits.Int(desc="Cutoff for highpass filtering")
    hp_sigma_vol = traits.Float(desc="Sigma volume for highpass filtering")
    evs_run = traits.Any(desc='task events')
    hpstring = traits.String(desc="op_string for highpass filtering")
    task_a_name = traits.String(desc="Task name")
    task_b_name = traits.String(desc="Task name")
    contrasts = traits.List(desc="T contrast array")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class FMRIGenSpec(BaseInterface):
    """
    Formats the fMRI parameters for FSL feat nodes.

    """
    
    input_spec = FMRIGenSpecInputSpec
    output_spec = FMRIGenSpecOutputSpec

    def _run_interface(self, runtime):

        if isdefined(self.inputs.hpcutoff):
            self.hpcutoff = self.inputs.hpcutoff
        elif self.inputs.design_block == 0:
            self.hpcutoff = self.inputs.task_duration + self.inputs.rest_duration
        else:
            self.hpcutoff = (self.inputs.task_duration + self.inputs.rest_duration) *2

        self.hp_sigma_vol = self.hpcutoff / (2 * self.inputs.TR)

        self.hpstring = '-bptf %f -1 -add %s' % (self.hp_sigma_vol, self.inputs.tempMean)

        if not isdefined(self.inputs.task_a_name):
            self.inputs.task_a_name = "TaskA"
        if not isdefined(self.inputs.task_b_name):
            self.inputs.task_b_name = "TaskB"

        if self.inputs.design_block == 0:
            self.contrasts = [['%s_versus_Rest' % self.inputs.task_a_name, 'T', [self.inputs.task_a_name], [1]]]

            self.evs_run = Bunch(
                conditions=[self.inputs.task_a_name],
                onsets=[list(range(self.inputs.rest_duration, int(self.inputs.TR * self.inputs.nvols),
                                   (self.inputs.task_duration + self.inputs.rest_duration)))],
                durations=[[self.inputs.task_duration]]
            )
        else:
            cont1 = ['%s_versus_%s' % (self.inputs.task_a_name, self.inputs.task_b_name), 'T', [self.inputs.task_a_name, self.inputs.task_b_name], [1, -1]]
            cont2 = ['%s_versus_%s' % (self.inputs.task_b_name, self.inputs.task_a_name), 'T', [self.inputs.task_a_name, self.inputs.task_b_name], [-1, 1]]
            self.contrasts = [cont1, cont2]

            self.evs_run = Bunch(
                conditions=[self.inputs.task_a_name, self.inputs.task_b_name],
                onsets=[list(range(self.inputs.rest_duration, int(self.inputs.TR * self.inputs.nvols), (self.inputs.task_duration * 2 + self.inputs.rest_duration * 2))),
                        list(range((self.inputs.rest_duration * 2 + self.inputs.task_duration), int(self.inputs.TR * self.inputs.nvols), (self.inputs.task_duration * 2 + self.inputs.rest_duration * 2)))
                        ],
                durations=[[self.inputs.task_duration], [self.inputs.task_duration]]
            )


        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['hpcutoff'] = self.hpcutoff
        outputs['hp_sigma_vol'] = self.hp_sigma_vol
        outputs['hpstring'] = self.hpstring
        outputs['evs_run'] = self.evs_run
        outputs['contrasts'] = self.contrasts
        outputs['task_a_name'] = self.inputs.task_a_name
        outputs['task_b_name'] = self.inputs.task_b_name
        return outputs
