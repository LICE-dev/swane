# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import Cluster


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.Cluster)  -*-
class FslCluster(Cluster):
    _cmd = "fsl-cluster"
