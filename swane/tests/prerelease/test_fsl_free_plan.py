"""The sweep plan on a host without FSL: nothing blocks, FSL-only values are
reported unreachable (never silently covered), FSL-free passes still run."""

import os

import pytest
from nipype.interfaces.fsl.base import FSLCommand

from swane.config import dependency_policy
from swane.resources import strings
from swane.tests.prerelease import capabilities as caps_mod
from swane.tests.prerelease.capabilities import Capabilities
from swane.tests.prerelease.plan import (
    _PASS_REQUIREMENTS,
    build_plan,
    coverage,
    gate_capabilities,
    plan_holes,
)
from swane.utils.DataInputList import DataInputList as DIL
from swane.utils.DependencyManager import (
    Dependence,
    DependenceStatus,
    DependencyManager,
)

FSL_ONLY = {"fsl", "xtract"}


def _no_fsl_caps() -> Capabilities:
    caps = Capabilities(cores=4, ram_gb=14.0)
    needed = gate_capabilities()
    needed.update({"dcm2niix", "fsaverage", "ram_budget", "slicer", "tractography"})
    needed.update(c for reqs in _PASS_REQUIREMENTS.values() for c in reqs)
    for name in needed - FSL_ONLY:
        caps.add(name, True, "assumed available in this test")
    for name in FSL_ONLY:
        caps.add(name, False, "no FSL on this host")
    return caps


@pytest.fixture
def no_fsl_host():
    return _no_fsl_caps()


def test_fsl_is_not_blocking_when_optional(no_fsl_host, monkeypatch):
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", False)
    assert caps_mod.blocking_failures(no_fsl_host) == []


def test_fsl_blocks_when_mandatory(no_fsl_host, monkeypatch):
    monkeypatch.setattr(dependency_policy, "FSL_MANDATORY", True)
    names = [item.name for item in caps_mod.blocking_failures(no_fsl_host)]
    assert names == ["fsl"]


def test_fsl_free_host_reports_fsl_values_unreachable(no_fsl_host):
    resolved = build_plan(no_fsl_host)
    report = coverage(resolved, no_fsl_host)
    assert plan_holes(report) == {}
    for axis_name, value in (
        ("deskull_engine", "BET"),
        ("registration_engine", "FSL"),
        ("fmri_engine", "FSL"),
        ("segmentation_engine", "FSL"),
        ("tractography_engine", "FSL_XTRACT"),
    ):
        assert value in report[axis_name].unreachable, (axis_name, value)
        assert value not in report[axis_name].covered, (axis_name, value)


#: The FSL-free-capable values whose only coverer used to be an FSL-pinned pass
#: (structural_alt_settings, dti_classic, dti_tractography_gpu).
FORMERLY_DEFERRED = (
    ("flat1", "false"),
    ("venous_mr_shape", "two_series"),
    ("electrode_threshold", "2500"),
    ("erode_kernel_size", "8"),
    ("tractography", "false"),
    ("cuda", "true"),
)


def test_fsl_free_host_defers_nothing(no_fsl_host):
    """With every non-FSL capability present, nothing is merely deferred: each
    value is either exercised by a running pass or reported unreachable."""
    resolved = build_plan(no_fsl_host, with_reconall=True)
    report = coverage(resolved, no_fsl_host)
    assert plan_holes(report) == {}
    deferred = {name: c.deferred for name, c in report.items() if c.deferred}
    assert deferred == {}, deferred
    for axis_name, value in FORMERLY_DEFERRED:
        assert value not in report[axis_name].deferred, (axis_name, value)
    for axis_name, value in FORMERLY_DEFERRED[:-1]:
        assert value in report[axis_name].covered, (axis_name, value)


def test_cuda_is_unreachable_without_fsl(no_fsl_host):
    """Only the FSL diffusion chain (eddy, BEDPOSTX, probtrackx) reads cuda, so
    on an FSL-free host both values are unreachable (cuda=true even with a
    GPU) -- never claimed by a pass whose engines ignore it."""
    report = coverage(build_plan(no_fsl_host), no_fsl_host)
    for value in ("false", "true"):
        assert value in report["cuda"].unreachable, value
        assert value not in report["cuda"].covered, value
    no_gpu = _no_fsl_caps()
    no_gpu.add("cuda", False, "no GPU detected")
    report = coverage(build_plan(no_gpu), no_gpu)
    assert "no GPU" in report["cuda"].unreachable["true"]


def test_fsl_free_host_still_runs_dipy_tractography(no_fsl_host):
    resolved = {item.name: item for item in build_plan(no_fsl_host)}
    assert not resolved["dti_tractography_dipy"].skipped, resolved[
        "dti_tractography_dipy"
    ].skip_reason
    # Not silently downgraded to tractography=false (the XTRACT-only gate did).
    assert resolved["dti_tractography_dipy"].values["tractography"] == "true"
    assert resolved["structural_fsl"].skipped
    assert resolved["fmri_task_and_rest_fsl"].skipped


# --------------------------------------------------------------------------- #
# Construction proof: every pass the plan runs without FSL builds a graph with
# no FSL command in it (niimath, which subclasses nipype's FSL maths classes
# but runs its own binary, is allowed) -- the same predicate as
# nipype_pipeline/test_fsl_free_main_workflow.py.
# --------------------------------------------------------------------------- #
def _is_niimath(interface) -> bool:
    return os.path.basename(str(getattr(interface, "_cmd", ""))).startswith("niimath")


def _stub_series() -> dict:
    """Manifest entries for every phantom folder ``subject._wiring`` can use."""
    series = {}
    for data_input in DIL:
        max_volumes = data_input.value.max_volumes
        series[str(data_input)] = {"n_vols": max_volumes if max_volumes > 0 else 40}
    # The two-series venous MR shape: one volume each.
    series["venous_mr_split_anat"] = {"n_vols": 1}
    series["venous_mr_split_angio"] = {"n_vols": 1}
    return series


FSL_FREE_PASSES = [item.name for item in build_plan(_no_fsl_caps()) if not item.skipped]


def _build_pass_graph(item, tmp_path, monkeypatch, with_fsl: bool) -> list:
    """Build the MainWorkflow of one resolved pass over a stub phantom exam
    and return its nodes (nothing is executed)."""
    from swane.nipype_pipeline.MainWorkflow import MainWorkflow
    from swane.tests.prerelease.subject import PhantomExam, prepare_subject

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    if with_fsl:
        monkeypatch.setenv("FSLOUTPUTTYPE", "NIFTI_GZ")
        found = Dependence(DependenceStatus.DETECTED, "FSL assumed in this test")
    else:
        monkeypatch.delenv("FSLDIR", raising=False)
        monkeypatch.delenv("FSLOUTPUTTYPE", raising=False)
        found = Dependence(DependenceStatus.MISSING, strings.check_dep_fsl_error)
    # prepare_subject writes SUBJECTS_DIR into os.environ; register it with
    # monkeypatch first so it is restored after the test.
    monkeypatch.setenv("SUBJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(DependencyManager, "check_fsl", staticmethod(lambda: found))
    dependency_manager = DependencyManager()
    assert dependency_manager.is_fsl() == with_fsl

    exam = PhantomExam(root=str(tmp_path / "phantom"), series=_stub_series())
    for folder in exam.series:
        os.makedirs(exam.folder(folder))

    subject_dir, global_config, subject_config, input_state_list = prepare_subject(
        item, exam, str(tmp_path / "work"), cores=4, ram_gb=14.0
    )
    workflow = MainWorkflow(
        name="fsl_free" if not with_fsl else "fsl",
        base_dir=subject_dir,
        global_config=global_config,
        subject_config=subject_config,
        dependency_manager=dependency_manager,
        subject_input_state_list=input_state_list,
        test_run=True,
    )
    nodes = workflow._get_all_nodes()
    assert nodes, "pass %s built an empty graph" % item.name
    return nodes


@pytest.mark.parametrize("pass_name", FSL_FREE_PASSES)
def test_fsl_free_pass_builds_without_fsl_nodes(pass_name, tmp_path, monkeypatch):
    item = {p.name: p for p in build_plan(_no_fsl_caps())}[pass_name]
    nodes = _build_pass_graph(item, tmp_path, monkeypatch, with_fsl=False)

    fsl_nodes = sorted(
        "%s (%s)" % (node.fullname, type(node.interface).__name__)
        for node in nodes
        if (
            isinstance(node.interface, FSLCommand)
            or type(node.interface).__module__.startswith("nipype.interfaces.fsl")
        )
        and not _is_niimath(node.interface)
    )
    assert fsl_nodes == [], "pass %s builds FSL nodes: %s" % (pass_name, fsl_nodes)


def test_fsl_free_stand_ins_run_without_fsl():
    """The FSL-free stand-ins replace their FSL originals on this host."""
    for name in ("structural_alt_settings_fsl_free", "dti_classic_fsl_free"):
        assert name in FSL_FREE_PASSES, name


def test_dti_classic_builds_eddy_correct_on_an_fsl_host(tmp_path, monkeypatch):
    """old_eddy_correct=true is covered only if the legacy eddy_correct node is
    really in dti_classic's graph (the dipy chain ignores the preference)."""
    from nipype.interfaces.fsl import EddyCorrect

    from swane.tests.prerelease.test_plan_integrity import _all_capable_caps

    caps = _all_capable_caps()
    item = {p.name: p for p in build_plan(caps)}["dti_classic"]
    assert not item.skipped, item.skip_reason
    nodes = _build_pass_graph(item, tmp_path, monkeypatch, with_fsl=True)
    eddy = [n.fullname for n in nodes if isinstance(n.interface, EddyCorrect)]
    assert eddy, "dti_classic builds no eddy_correct node"


def test_dti_synthmorph_builds_the_fsl_diffusion_chain_with_synth(
    tmp_path, monkeypatch
):
    """dti_synthmorph covers old_eddy_correct=false and the probtrackx transform
    bridge with SYNTH registration only if its graph really holds eddy,
    BEDPOSTX and probtrackx next to SynthStrip/SynthMorph nodes."""
    from nipype.interfaces.fsl import BEDPOSTX5, ProbTrackX2

    from swane.nipype_pipeline.interfaces.freesurfer.SynthMorphApply import (
        SynthMorphApply,
    )
    from swane.nipype_pipeline.interfaces.freesurfer.SynthMorphReg import (
        SynthMorphReg,
    )
    from swane.nipype_pipeline.interfaces.freesurfer.SynthStrip import SynthStrip
    from swane.nipype_pipeline.interfaces.fsl.CustomEddy import CustomEddy
    from swane.nipype_pipeline.workflows import tractography_workflow
    from swane.tests.prerelease.subject import SWEEP_TRACT
    from swane.tests.prerelease.test_plan_integrity import _all_capable_caps

    # A stub XTRACT protocol for the sweep tract, so probtrackx is built on a
    # host (or CI runner) without the FSL data: construction only checks that
    # the seed and target files exist.
    xtract = tmp_path / "xtract"
    for side in ("l", "r"):
        protocol = xtract / ("%s_%s" % (SWEEP_TRACT, side))
        protocol.mkdir(parents=True)
        for name in ("seed.nii.gz", "target.nii.gz", "exclude.nii.gz"):
            (protocol / name).write_bytes(b"")
    monkeypatch.setattr(tractography_workflow, "XTRACT_DATA_DIR", str(xtract))

    item = {p.name: p for p in build_plan(_all_capable_caps())}["dti_synthmorph"]
    assert not item.skipped, item.skip_reason
    nodes = _build_pass_graph(item, tmp_path, monkeypatch, with_fsl=True)

    def built(interface_class):
        return [n.fullname for n in nodes if isinstance(n.interface, interface_class)]

    assert built(CustomEddy), "dti_synthmorph builds no eddy node"
    assert built(BEDPOSTX5), "dti_synthmorph builds no BEDPOSTX node"
    assert built(ProbTrackX2), "dti_synthmorph builds no probtrackx node"
    assert built(SynthStrip), "dti_synthmorph builds no SynthStrip node"
    assert built(SynthMorphReg), "dti_synthmorph builds no SynthMorph registration"
    assert built(SynthMorphApply), "dti_synthmorph applies no SynthMorph transform"
