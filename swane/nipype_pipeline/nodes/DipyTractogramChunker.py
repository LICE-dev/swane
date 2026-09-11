# -*- DISCLAIMER: this file contains code derived from Nipype (https://github.com/nipy/nipype/blob/master/LICENSE)  -*-
"""
Split an atlas-space tractogram into 1..N **representative** sub-tractograms.

RecoBundles' expensive build (:class:`~swane.nipype_pipeline.nodes.
DipyRecoBundles.DipyRecoBundlesBuild`) clusters a whole tractogram. To bound its
peak memory, the tractogram can be built in several smaller pieces and the
per-piece recognitions unioned back (:class:`~swane.nipype_pipeline.nodes.
DipyBundleUnion.DipyBundleUnion`). For that union to approximate the
whole-tractogram result, each piece must be a **representative** sample of the
global anatomy, not a contiguous slice: a contiguous block would over-represent
whatever region the tractogram happens to store together and starve the others.

So the split is **strided**: chunk ``c`` gets streamlines ``c, c+N, 2N+c, ...``.
This partitions the tractogram exactly once (every streamline in exactly one
chunk) while spreading each chunk across the whole ordering. ``n_chunks == 1``
(the default) is a pass-through: the single "chunk" is the input tractogram
itself, so no copy is written and the streamlines are stored only once.

The maximum useful ``n_chunks`` for a given streamline count is a RAM-estimator
decision (E3B, deferred); this node simply honours the ``n_chunks`` it is given.
"""

import os
from os.path import abspath, basename

import numpy as np
from nipype.interfaces.base import (
    traits,
    BaseInterface,
    BaseInterfaceInputSpec,
    TraitedSpec,
    File,
    isdefined,
)


def _strip_tractogram_ext(name):
    for ext in (".trx", ".trk", ".tck"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterfaceInputSpec)  -*-
class DipyTractogramChunkerInputSpec(BaseInterfaceInputSpec):
    tractogram_atlas = File(
        exists=True,
        mandatory=True,
        desc="the atlas-space whole-brain tractogram to split (.trx)",
    )
    n_chunks = traits.Int(
        1,
        usedefault=True,
        desc="number of representative sub-tractograms to produce (>=1); 1 is a "
        "pass-through of the whole tractogram",
    )
    out_prefix = traits.Str(desc="basename prefix for the written chunk files")


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.TraitedSpec)  -*-
class DipyTractogramChunkerOutputSpec(TraitedSpec):
    # A plain List, not OutputMultiPath: OutputMultiPath/OutputMultiObject
    # unwraps a length-1 list to a bare string on read (see
    # nipype.interfaces.base.traits_extension.OutputMultiObject.get), which
    # would silently turn "chunks" into a bare path string whenever n_chunks
    # == 1 (the default) -- breaking every downstream connection that expects
    # a list, e.g. dipy_bundle_workflow's ("recobundles_chunks", _first).
    chunks = traits.List(
        File(exists=True),
        desc="the 1..N representative sub-tractograms (.trx); the input itself "
        "when n_chunks == 1",
    )


# -*- DISCLAIMER: this class extends a Nipype class (nipype.interfaces.base.BaseInterface)  -*-
class DipyTractogramChunker(BaseInterface):
    """
    Partitions an atlas-space tractogram into ``n_chunks`` representative
    (strided, never contiguous) sub-tractograms for a shared RecoBundles build,
    passing the input through unchanged when ``n_chunks == 1``.

    """

    input_spec = DipyTractogramChunkerInputSpec
    output_spec = DipyTractogramChunkerOutputSpec

    # A plain streamline re-slice + write; comparable to the tractogram size.
    _mem_gb = 2.0

    def _run_interface(self, runtime):
        n_chunks = int(self.inputs.n_chunks)
        if n_chunks < 1:
            raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")

        # n_chunks == 1 is a pass-through: no file is written, so the output list
        # is just the input path (resolved in _list_outputs).
        if n_chunks == 1:
            return runtime

        from dipy.io.streamline import load_tractogram, save_tractogram

        sft = load_tractogram(
            self.inputs.tractogram_atlas, "same", bbox_valid_check=False
        )
        n = len(sft.streamlines)
        for c, out in enumerate(self._chunk_filenames(n_chunks)):
            idx = np.arange(c, n, n_chunks)
            save_tractogram(sft[idx], out, bbox_valid_check=False)

        return runtime

    def _prefix(self):
        if isdefined(self.inputs.out_prefix):
            return str(self.inputs.out_prefix)
        base = _strip_tractogram_ext(basename(self.inputs.tractogram_atlas))
        return f"chunk_{base}"

    def _chunk_filenames(self, n_chunks):
        prefix = self._prefix()
        return [abspath(f"{prefix}_{c}of{n_chunks}.trx") for c in range(n_chunks)]

    def _list_outputs(self):
        outputs = self.output_spec().get()
        n_chunks = int(self.inputs.n_chunks)
        if n_chunks == 1:
            outputs["chunks"] = [abspath(self.inputs.tractogram_atlas)]
        else:
            outputs["chunks"] = self._chunk_filenames(n_chunks)
        return outputs
