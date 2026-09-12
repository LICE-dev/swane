# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Transform a recognised bundle from atlas space to reference space and write ``.vtp``.

RecoBundles recognises each bundle in the atlas (model) world space; the whole
subject tractogram was brought there once by the Phase-1 whole-brain SLR, whose
inverse ``atlas2native`` transform Phase 1 published. This node applies that 4x4
transform to the recognised streamlines (``dipy.tracking.streamline.
transform_streamlines``) and writes the result as VTK PolyData (``.vtp``) in the
**reference space** -- the result contract 3D Slicer reads natively as a model
(spec section 7).

The PolyData is written with ``vtk`` **directly**. dipy's ``save_tractogram``
can emit ``.vtp`` too, but only through ``dipy.io.vtk``, whose ``fury`` backend
is an optional package that SWANe does not install; ``vtk`` itself is already
present transitively, so this node uses it and never imports ``fury``.

A generic ``.vtk``/``.vtp`` model file carries no coordinate-system metadata,
and both dipy's own vtk writer (``dipy.io.vtk.save_vtk_streamlines``) and 3D
Slicer's generic model reader treat such files as LPS. The points this node
writes are therefore converted from the RASMM world space
``transform_streamlines`` works in to LPS (``x, y`` negated) right before
they reach ``vtk``.
"""

import os
from os.path import abspath

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)

VTP_EXTENSION = ".vtp"

# RAS millimetre -> LPS millimetre: negate the first two (x, y) coordinates,
# the convention plain VTK model files (and 3D Slicer's generic model reader)
# assume.
RAS_TO_LPS = np.diag([-1.0, -1.0, 1.0])


def write_streamlines_vtp(streamlines, path):
    """Write ``streamlines`` (an iterable of Nx3 RASMM arrays) as VTK PolyData
    lines in LPS millimetres.

    Uses ``vtk`` directly (no ``fury``): one polyline cell per streamline, all
    points in a single ``vtkPoints`` array. An empty bundle writes a valid,
    loadable PolyData with zero lines.
    """
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkIOXML import vtkXMLPolyDataWriter
    from vtkmodules.util.numpy_support import numpy_to_vtk

    lines = vtkCellArray()
    blocks = []
    offset = 0
    for streamline in streamlines:
        arr = np.asarray(streamline, dtype=np.float32) @ RAS_TO_LPS.T.astype(np.float32)
        n = len(arr)
        if n == 0:
            continue
        blocks.append(arr)
        lines.InsertNextCell(n)
        for i in range(n):
            lines.InsertCellPoint(offset + i)
        offset += n

    if blocks:
        all_points = np.vstack(blocks).astype(np.float32)
    else:
        all_points = np.zeros((0, 3), dtype=np.float32)

    points = vtkPoints()
    points.SetData(numpy_to_vtk(all_points, deep=True))

    polydata = vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetLines(lines)

    writer = vtkXMLPolyDataWriter()
    writer.SetFileName(path)
    writer.SetInputData(polydata)
    writer.Write()


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyBundlesToRefInputSpec(BaseInterfaceInputSpec):
    bundle = File(
        exists=True,
        mandatory=True,
        desc="the recognised bundle in atlas space (.trx)",
    )
    atlas2native = File(
        exists=True,
        mandatory=True,
        desc="text file with the 4x4 atlas->native (reference) transform",
    )
    out_name = traits.Str(
        mandatory=True,
        desc="output basename without extension, e.g. 'r-af_lh'",
    )
    out_vtp = File(desc="the reference-space bundle output (.vtp)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyBundlesToRefOutputSpec(TraitedSpec):
    bundle_vtp = File(
        desc="the recognised bundle in reference space (.vtp), written with vtk"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyBundlesToRef(BaseInterface):
    """
    Transforms a recognised atlas-space bundle into reference space with the
    Phase-1 ``atlas2native`` transform and writes it as a ``.vtp`` (VTK PolyData,
    via ``vtk`` directly -- never ``fury``, LPS millimetres), the format 3D
    Slicer reads natively.

    """

    input_spec = DipyBundlesToRefInputSpec
    output_spec = DipyBundlesToRefOutputSpec

    _mem_gb = 1.0

    def _run_interface(self, runtime):
        from dipy.io.streamline import load_tractogram
        from dipy.tracking.streamline import transform_streamlines

        sft = load_tractogram(self.inputs.bundle, "same", bbox_valid_check=False)
        sft.to_rasmm()
        matrix = np.loadtxt(self.inputs.atlas2native)

        ref_streamlines = transform_streamlines(sft.streamlines, matrix)
        write_streamlines_vtp(ref_streamlines, self._gen_outfilename())
        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_vtp
        if not isdefined(out_file):
            out_file = str(self.inputs.out_name) + VTP_EXTENSION
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        outputs["bundle_vtp"] = self._gen_outfilename()
        return outputs
