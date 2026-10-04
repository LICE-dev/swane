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
    AXES,
    _PASS_REQUIREMENTS,
    build_plan,
    coverage,
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
    needed = {gate for axis in AXES for gate in axis.gates.values()}
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


@pytest.mark.parametrize("pass_name", FSL_FREE_PASSES)
def test_fsl_free_pass_builds_without_fsl_nodes(pass_name, tmp_path, monkeypatch):
    from swane.nipype_pipeline.MainWorkflow import MainWorkflow
    from swane.tests.prerelease.subject import PhantomExam, prepare_subject

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("FSLDIR", raising=False)
    monkeypatch.delenv("FSLOUTPUTTYPE", raising=False)
    # prepare_subject writes SUBJECTS_DIR into os.environ; register it with
    # monkeypatch first so it is restored after the test.
    monkeypatch.setenv("SUBJECTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        DependencyManager,
        "check_fsl",
        staticmethod(
            lambda: Dependence(DependenceStatus.MISSING, strings.check_dep_fsl_error)
        ),
    )
    dependency_manager = DependencyManager()
    assert not dependency_manager.is_fsl()

    item = {p.name: p for p in build_plan(_no_fsl_caps())}[pass_name]
    exam = PhantomExam(root=str(tmp_path / "phantom"), series=_stub_series())
    for folder in exam.series:
        os.makedirs(exam.folder(folder))

    subject_dir, global_config, subject_config, input_state_list = prepare_subject(
        item, exam, str(tmp_path / "work"), cores=4, ram_gb=14.0
    )
    workflow = MainWorkflow(
        name="fsl_free",
        base_dir=subject_dir,
        global_config=global_config,
        subject_config=subject_config,
        dependency_manager=dependency_manager,
        subject_input_state_list=input_state_list,
        test_run=True,
    )
    nodes = workflow._get_all_nodes()
    assert nodes, "pass %s built an empty graph" % pass_name

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
