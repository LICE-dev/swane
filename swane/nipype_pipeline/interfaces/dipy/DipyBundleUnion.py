# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Union of the per-chunk recognitions of one tract/side back into one bundle.

When a tractogram is split into N representative sub-tractograms
(:class:`~swane.nipype_pipeline.interfaces.dipy.DipyTractogramChunker.DipyTractogramChunker`)
and each is recognised independently
(:class:`~swane.nipype_pipeline.interfaces.dipy.DipyRecoBundles.DipyRecoBundlesRecognize`),
this node concatenates the N recognised partial bundles into the single
recognised bundle for that tract/side. All partials are in the same atlas
(model) world space, so the union is a plain streamline concatenation.

When there is only one partial (``n_chunks == 1``) it is a pass-through: the
single input is the output, so no file is rewritten and the streamlines are
stored only once.
"""

import os
from os.path import abspath, basename

from nipype.interfaces.base import (
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    InputMultiPath,
    isdefined,
)


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyBundleUnionInputSpec(BaseInterfaceInputSpec):
    recognized_bundles = InputMultiPath(
        File(exists=True),
        mandatory=True,
        desc="the N per-chunk recognised partial bundles for one tract/side "
        "(.trx, atlas space)",
    )
    out_bundle = File(desc="the unioned recognised bundle output (.trx)")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyBundleUnionOutputSpec(TraitedSpec):
    bundle = File(
        desc="the recognised bundle for the tract/side (.trx, atlas space): the "
        "concatenation of the N partials, or the single input when N == 1"
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyBundleUnion(BaseInterface):
    """
    Concatenates the N per-chunk recognised partial bundles for one tract/side
    into a single atlas-space bundle, passing the input through unchanged when
    there is only one partial.

    """

    input_spec = DipyBundleUnionInputSpec
    output_spec = DipyBundleUnionOutputSpec

    def _run_interface(self, runtime):
        partials = list(self.inputs.recognized_bundles)

        # A single partial is a pass-through: no file is rewritten.
        if len(partials) == 1:
            return runtime

        from dipy.io.streamline import load_tractogram, save_tractogram
        from dipy.io.stateful_tractogram import StatefulTractogram
        from dipy.tracking.streamline import Streamlines

        first_sft = load_tractogram(partials[0], "same", bbox_valid_check=False)
        first_sft.to_rasmm()
        union = Streamlines(first_sft.streamlines)
        for path in partials[1:]:
            sft = load_tractogram(path, "same", bbox_valid_check=False)
            sft.to_rasmm()
            union.extend(sft.streamlines)

        union_sft = StatefulTractogram.from_sft(union, first_sft)
        save_tractogram(union_sft, self._gen_outfilename(), bbox_valid_check=False)
        return runtime

    def _gen_outfilename(self):
        out_file = self.inputs.out_bundle
        if not isdefined(out_file):
            base = basename(self.inputs.recognized_bundles[0])
            out_file = f"union_{base}"
        return abspath(out_file)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        partials = list(self.inputs.recognized_bundles)
        if len(partials) == 1:
            outputs["bundle"] = abspath(partials[0])
        else:
            outputs["bundle"] = self._gen_outfilename()
        return outputs
