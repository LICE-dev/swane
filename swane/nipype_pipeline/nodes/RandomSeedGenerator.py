# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.base import (traits, BaseInterface, BaseInterfaceInputSpec, TraitedSpec, File)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class RandomSeedGeneratorInputSpec(BaseInterfaceInputSpec):
    seeds_n = traits.Int(mandatory=True, desc="The number of needed seeds")
    mask = File(mandatory=True, exists=True, desc="Just for depend")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class RandomSeedGeneratorOutputSpec(TraitedSpec):
    seeds = traits.List(desc='the list of seeds')


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class RandomSeedGenerator(BaseInterface):
    """
    Generates a list of random integers. Used to obtains a series of random seeds.

    """
    
    input_spec = RandomSeedGeneratorInputSpec
    output_spec = RandomSeedGeneratorOutputSpec
    seed_list = []

    def _run_interface(self, runtime):
        from random import randrange
        for x in range(self.inputs.seeds_n):
            self.seed_list.append(randrange(1000))

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs['seeds'] = self.seed_list
        return outputs
