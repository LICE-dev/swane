# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    Bunch,
    isdefined,
)
from swane.config.config_enums import BlockDesign


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class FMRIGenSpecInputSpec(BaseInterfaceInputSpec):
    TR = traits.Float(mandatory=True, desc="Repetition Time")
    nvols = traits.Int(mandatory=True, desc="Number of EPI runs")
    task_duration = traits.Int(mandatory=True, desc="Task duration")
    rest_duration = traits.Int(mandatory=True, desc="Rest duration")
    block_design = traits.Enum(BlockDesign, usedefault=True)
    task_a_name = traits.String(mandatory=False, desc="Task A name")
    task_b_name = traits.String(mandatory=False, desc="Task A name")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class FMRIGenSpecOutputSpec(TraitedSpec):
    evs_run = traits.Any(desc="task events")
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

        if not isdefined(self.inputs.task_a_name):
            self.inputs.task_a_name = "TaskA"
        if not isdefined(self.inputs.task_b_name):
            self.inputs.task_b_name = "TaskB"

        if self.inputs.block_design == BlockDesign.RARA:
            self.contrasts = [
                [
                    "%s_versus_Rest" % self.inputs.task_a_name,
                    "T",
                    [self.inputs.task_a_name],
                    [1],
                ]
            ]

            self.evs_run = Bunch(
                conditions=[self.inputs.task_a_name],
                onsets=[
                    list(
                        range(
                            self.inputs.rest_duration,
                            int(self.inputs.TR * self.inputs.nvols),
                            (self.inputs.task_duration + self.inputs.rest_duration),
                        )
                    )
                ],
                durations=[[self.inputs.task_duration]],
            )
        else:
            cont1 = [
                "%s_versus_%s" % (self.inputs.task_a_name, self.inputs.task_b_name),
                "T",
                [self.inputs.task_a_name, self.inputs.task_b_name],
                [1, -1],
            ]
            cont2 = [
                "%s_versus_%s" % (self.inputs.task_b_name, self.inputs.task_a_name),
                "T",
                [self.inputs.task_a_name, self.inputs.task_b_name],
                [-1, 1],
            ]
            self.contrasts = [cont1, cont2]

            self.evs_run = Bunch(
                conditions=[self.inputs.task_a_name, self.inputs.task_b_name],
                onsets=[
                    list(
                        range(
                            self.inputs.rest_duration,
                            int(self.inputs.TR * self.inputs.nvols),
                            (
                                self.inputs.task_duration * 2
                                + self.inputs.rest_duration * 2
                            ),
                        )
                    ),
                    list(
                        range(
                            (self.inputs.rest_duration * 2 + self.inputs.task_duration),
                            int(self.inputs.TR * self.inputs.nvols),
                            (
                                self.inputs.task_duration * 2
                                + self.inputs.rest_duration * 2
                            ),
                        )
                    ),
                ],
                durations=[[self.inputs.task_duration], [self.inputs.task_duration]],
            )

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["evs_run"] = self.evs_run
        outputs["contrasts"] = self.contrasts
        outputs["task_a_name"] = self.inputs.task_a_name
        outputs["task_b_name"] = self.inputs.task_b_name
        return outputs
