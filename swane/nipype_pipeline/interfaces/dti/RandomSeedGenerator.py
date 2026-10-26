# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
)

# Seed bounds: the seeds become probtrackx2 --rseed values, read as a C int, so
# they stay positive and within a signed 32-bit int.
MIN_SEED = 1
MAX_SEED = 2**31 - 1


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class RandomSeedGeneratorInputSpec(BaseInterfaceInputSpec):
    seeds_n = traits.Int(mandatory=True, desc="The number of needed seeds")
    mask = File(mandatory=True, exists=True, desc="Just for depend")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class RandomSeedGeneratorOutputSpec(TraitedSpec):
    seeds = traits.List(desc="the list of seeds")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class RandomSeedGenerator(BaseInterface):
    """
    Generates a list of distinct random integers in ``[MIN_SEED, MAX_SEED)``,
    one probtrackx2 seed per parallel run.

    The seeds are drawn without replacement: two equal seeds would make two runs
    identical, and SumMultiTracks would count that realisation twice.

    """

    input_spec = RandomSeedGeneratorInputSpec
    output_spec = RandomSeedGeneratorOutputSpec
    seed_list: list

    def _run_interface(self, runtime):
        from random import sample

        self.seed_list = sample(range(MIN_SEED, MAX_SEED), self.inputs.seeds_n)

        return runtime

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["seeds"] = self.seed_list
        return outputs
