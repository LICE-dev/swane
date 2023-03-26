# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.freesurfer import Label2Vol
from os.path import abspath


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.freesurfer.Label2Vol)  -*-
class CustomLabel2Vol(Label2Vol):

    def _list_outputs(self):
        outputs = super(CustomLabel2Vol, self)._list_outputs()
        outputs["vol_label_file"] = abspath(outputs["vol_label_file"])
        return outputs
