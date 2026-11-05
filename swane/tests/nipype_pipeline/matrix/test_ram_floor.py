"""Fixed RAM reservations versus the RAM floor of a subject tab.

nipype's pre-run check aborts the whole subject workflow when a single node
reserves more RAM than the subject tab budget (``ram_gb``). A node may reserve
more than ``ResourceManager.MINIMUM_SUBJECT_RAM`` (the ``ram_gb`` range
minimum) only if a ``ram_gb`` requirement in the preference catalog gates it
(engine option or Synth recon-all). This test reads the reservations from the
committed matrix snapshots, so a new or raised reservation of an ungated node
fails here instead of at run time.
"""

import os
import re

from swane.utils.ResourceManager import ResourceManager

SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")

#: Interfaces that run only when the ram_gb requirement of their preference is
#: met: Synth tools (SynthStrip/SynthMorph/SynthSeg engines), antspynet brain
#: extraction and the dipy tractography engine.
GATED_INTERFACES = {
    "SynthStrip",
    "SynthMorphReg",
    "SynthSeg",
    "AntsPyNetBrainExtraction",
    "DipyTractogramChunker",
    "DipyRecoBundlesBuild",
    "DipyRecoBundlesRecognize",
    "DipyBundleRecovery",
    "DipyAtlasSLR",
    "DipyTracking",
}

#: Snapshots of Synth recon-all (synth.reconall, gated by its ram_gb
#: requirement): classic recon-all has no requirement and is checked.
GATED_SNAPSHOTS = {"reconall_synth_tools.txt", "reconall_synth_tools_test_run.txt"}

_NODE_LINE = re.compile(r"^\s*- (\S+) \[(\w+)\].* mem_gb=([0-9.]+)")


def _reservations():
    for root, _, files in os.walk(SNAPSHOTS_DIR):
        for fname in files:
            if not fname.endswith(".txt"):
                continue
            with open(os.path.join(root, fname)) as snapshot:
                for line in snapshot:
                    match = _NODE_LINE.match(line)
                    if match:
                        node, interface, mem_gb = match.groups()
                        yield fname, node, interface, float(mem_gb)


def test_snapshots_carry_reservations():
    # Guard against a renderer change that would make the check below vacuous
    assert any(mem_gb > 1 for *_, mem_gb in _reservations())


def test_only_gated_nodes_reserve_more_than_the_ram_floor():
    # e.g. classic recon-all, segment_ha and nonaggr_denoising (5 GB) and
    # FSL FAST (4 GB) have no ram_gb requirement
    over_floor = {
        (fname, node, interface, mem_gb)
        for fname, node, interface, mem_gb in _reservations()
        if mem_gb > ResourceManager.MINIMUM_SUBJECT_RAM
        and interface not in GATED_INTERFACES
        and fname not in GATED_SNAPSHOTS
    }
    assert not over_floor
