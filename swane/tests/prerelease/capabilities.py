"""What this machine can actually run.

The pre-release suite sweeps configuration axes that each need something from
the host: FreeSurfer for recon-all, a GPU for the CUDA paths, enough RAM for
the Synth tools, the XTRACT protocol data for real tractography, Slicer for
the venous-CT endocranium segmentation.

Nothing here *fails* when something is missing: an unavailable axis is dropped
from the plan with an explicit, printable reason, so a run on a partially
equipped box still exercises everything that box can do. The reasons are part
of the report — a pass that never ran must never be mistaken for one that ran
and succeeded.

RAM thresholds are not reinvented: they come from
:class:`~swane.utils.ResourceManager.ResourceManager`, the same source the
application itself uses to enable or grey out these preferences.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

from swane.config.preference_list import XTRACT_DATA_DIR
from swane.utils.DependencyManager import DependencyManager
from swane.utils.ResourceManager import ResourceManager


@dataclass(frozen=True)
class Capability:
    """One host feature, and why it is (not) usable."""

    name: str
    available: bool
    reason: str

    def __str__(self) -> str:
        mark = "yes" if self.available else "no "
        return "  [%s] %-22s %s" % (mark, self.name, self.reason)


@dataclass
class Capabilities:
    """The full probe result, keyed by feature name."""

    items: dict = field(default_factory=dict)
    #: RAM the user allocated to the runs, in GB (drives the Synth thresholds).
    ram_gb: float = 0.0
    #: CPU cores the user allocated to the runs.
    cores: int = 0

    def add(self, name: str, available: bool, reason: str) -> None:
        self.items[name] = Capability(name, available, reason)

    def has(self, name: str) -> bool:
        item = self.items.get(name)
        return bool(item and item.available)

    def reason(self, name: str) -> str:
        item = self.items.get(name)
        return item.reason if item else "not probed"

    def missing(self) -> list:
        return [c for c in self.items.values() if not c.available]

    def describe(self) -> str:
        lines = [
            "Host capabilities (cores=%d, ram=%.1f GB):" % (self.cores, self.ram_gb)
        ]
        lines.extend(str(self.items[k]) for k in sorted(self.items))
        return "\n".join(lines)


def _probe_fsl(dependency_manager: DependencyManager, caps: Capabilities) -> None:
    caps.add(
        "fsl",
        dependency_manager.is_fsl(),
        (
            "FSL %s" % os.environ.get("FSLDIR", "?")
            if dependency_manager.is_fsl()
            else "no usable FSL (>= %s) found; nothing can run"
            % DependencyManager.MIN_FSL_VERSION
        ),
    )


def _probe_dcm2niix(dependency_manager: DependencyManager, caps: Capabilities) -> None:
    caps.add(
        "dcm2niix",
        dependency_manager.is_dcm2niix(),
        (
            "available"
            if dependency_manager.is_dcm2niix()
            else "missing; phantom DICOM cannot be converted"
        ),
    )


def _probe_freesurfer(
    dependency_manager: DependencyManager, caps: Capabilities
) -> None:
    has_fs = dependency_manager.is_freesurfer()
    caps.add(
        "freesurfer",
        has_fs,
        (
            "FreeSurfer at %s" % os.environ.get("FREESURFER_HOME", "?")
            if has_fs
            else "no FreeSurfer (>= %s); recon-all/SynthSeg axes are dropped"
            % DependencyManager.MIN_FREESURFER_VERSION
        ),
    )

    # The hippocampal/amygdala subfield step needs the Matlab runtime.
    has_matlab = has_fs and dependency_manager.is_freesurfer_matlab()
    caps.add(
        "freesurfer_matlab",
        has_matlab,
        (
            "Matlab runtime present"
            if has_matlab
            else "no FreeSurfer Matlab runtime; hippo/amygdala labels are dropped"
        ),
    )

    # SynthStrip/SynthSeg/SynthMorph ship with recent FreeSurfer only.
    has_synth = has_fs and DependencyManager.is_freesurfer_synth()
    caps.add(
        "freesurfer_synth",
        has_synth,
        (
            "Synth tools present (FreeSurfer >= %s)"
            % DependencyManager.SYNTH_FREESURFER_VERSION
            if has_synth
            else "FreeSurfer < %s; Synth tool axes are dropped"
            % DependencyManager.SYNTH_FREESURFER_VERSION
        ),
    )


def _probe_synth_ram(caps: Capabilities) -> None:
    """Each Synth tool has its own RAM floor; check the allocated budget."""
    has_synth = caps.has("freesurfer_synth")
    for name, needed in (
        ("synth_strip", ResourceManager.synth_strip_ram_requirements()),
        ("synth_morph", ResourceManager.synth_morph_ram_requirements()),
        ("synth_seg", ResourceManager.synth_seg_ram_requirements()),
        ("synth_reconall", ResourceManager.synth_reconall_ram_requirements()),
    ):
        if not has_synth:
            caps.add(name, False, "requires the FreeSurfer Synth tools")
            continue
        enough = caps.ram_gb >= needed
        caps.add(
            name,
            enough,
            (
                "%.1f GB allocated >= %.1f GB required" % (caps.ram_gb, needed)
                if enough
                else "needs %.1f GB, only %.1f GB allocated" % (needed, caps.ram_gb)
            ),
        )


def _probe_gpu(caps: Capabilities) -> None:
    try:
        is_cuda = ResourceManager.is_cuda()
    except Exception:
        is_cuda = False
    caps.add(
        "cuda",
        is_cuda,
        "GPU detected" if is_cuda else "no GPU detected; CUDA axes are dropped",
    )


def _probe_xtract(caps: Capabilities) -> None:
    # A real tract graph needs the per-tract protocol folders. The suite only
    # sweeps the corticospinal tract, so that is what must be present.
    tract_dir = os.path.join(XTRACT_DATA_DIR, "cst_l") if XTRACT_DATA_DIR else ""
    ok = bool(XTRACT_DATA_DIR) and os.path.isdir(tract_dir)
    caps.add(
        "xtract",
        ok,
        (
            "XTRACT protocols at %s" % XTRACT_DATA_DIR
            if ok
            else "no XTRACT protocol data; the tractography axis is dropped"
        ),
    )


def _probe_mni(caps: Capabilities) -> None:
    """MNI standard templates, read at construction by several branches."""
    fsldir = os.environ.get("FSLDIR")
    needed = [
        "MNI152_T1_1mm.nii.gz",
        "MNI152_T1_1mm_brain.nii.gz",
        "MNI152_T1_2mm_brain.nii.gz",
    ]
    missing = []
    if not fsldir:
        missing = needed
    else:
        for name in needed:
            if not os.path.isfile(os.path.join(fsldir, "data", "standard", name)):
                missing.append(name)
    caps.add(
        "mni_templates",
        not missing,
        (
            "MNI standard templates present"
            if not missing
            else "missing %s; FLAT1/AI/tractography/AROMA axes are dropped"
            % ", ".join(missing)
        ),
    )


def _probe_slicer(global_config, caps: Capabilities) -> None:
    try:
        ok = DependencyManager.is_slicer(global_config)
    except Exception:
        ok = False
    caps.add(
        "slicer",
        ok,
        (
            "Slicer configured"
            if ok
            else "no valid Slicer path in the global config; venous CT is dropped"
        ),
    )


def _probe_ram_budget(caps: Capabilities) -> None:
    """The allocated budget must exist physically, or nipype will thrash/OOM."""
    total = ResourceManager.total_memory_gb()
    ok = caps.ram_gb <= total
    caps.add(
        "ram_budget",
        ok,
        (
            "%.1f GB of %.1f GB physical" % (caps.ram_gb, total)
            if ok
            else "asked for %.1f GB but the machine has %.1f GB; lower --ram"
            % (caps.ram_gb, total)
        ),
    )


def _probe_freesurfer_subject(caps: Capabilities) -> None:
    """The phantom anatomy is derived from the fsaverage subject."""
    fs_home = os.environ.get("FREESURFER_HOME")
    path = os.path.join(fs_home, "subjects", "fsaverage") if fs_home else ""
    ok = bool(fs_home) and os.path.isdir(path)
    caps.add(
        "fsaverage",
        ok,
        (
            "fsaverage present"
            if ok
            else "no $FREESURFER_HOME/subjects/fsaverage; the phantom cannot be built"
        ),
    )


def probe(global_config=None, cores: int = 0, ram_gb: float = 0.0) -> Capabilities:
    """Probe the host for everything the pre-release sweep depends on.

    Parameters
    ----------
    global_config : ConfigManager, optional
        Used only for the Slicer path, which lives in the application settings.
    cores, ram_gb
        The budget the user allocated; the Synth thresholds are checked against
        ``ram_gb`` rather than against total system memory, because that is what
        the workflows will actually be allowed to use.
    """
    caps = Capabilities(cores=cores, ram_gb=ram_gb)
    dependency_manager = DependencyManager()

    _probe_fsl(dependency_manager, caps)
    _probe_dcm2niix(dependency_manager, caps)
    _probe_freesurfer(dependency_manager, caps)
    _probe_freesurfer_subject(caps)
    _probe_ram_budget(caps)
    _probe_synth_ram(caps)
    _probe_gpu(caps)
    _probe_xtract(caps)
    _probe_mni(caps)
    _probe_slicer(global_config, caps)

    caps.add(
        "graphviz",
        shutil.which("dot") is not None,
        "dot available" if shutil.which("dot") else "no graphviz; graphs are skipped",
    )
    return caps


#: Capabilities without which nothing can run at all.
BLOCKING = ("fsl", "dcm2niix", "fsaverage", "ram_budget")


def blocking_failures(caps: Capabilities) -> list:
    """Return the capabilities that make a run pointless, if any."""
    return [caps.items[name] for name in BLOCKING if not caps.has(name)]
