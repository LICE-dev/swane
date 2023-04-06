# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-

from nipype.interfaces.fsl import  DilateImage
from nipype.interfaces.fsl.maths import KernelInput


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.fsl.DilateImage)  -*-
class CustomDilateImage(DilateImage):
    """
    Custom implementation of DilateImage Nipype Node use Kernel input as input_spec.

    """
    
    input_spec = KernelInput
