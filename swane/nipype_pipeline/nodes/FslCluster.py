# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import Cluster


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.Cluster)  -*-
#TODO verificare utilità
class FslCluster(Cluster):
    """
    Custom implementation of Cluster Nipype Node to use fsl-cluster command instead of Cluster command.

    """
    
    _cmd = "fsl-cluster"
