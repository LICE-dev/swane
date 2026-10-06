"""The default engines assemble a MainWorkflow that never runs an FSL tool.

With ``FSL_MANDATORY = False`` FSL is only a recommended dependency, so a
subject with every input loaded must build a graph whose command-line nodes are
all FSL-free when FSL is missing. niimath-backed interfaces subclass Nipype's
FSL maths classes but run the bundled niimath binary, so they are allowed; they
must also pin the compressed NIFTI_GZ output type, which Nipype would otherwise
take from the (missing) FSL environment.
"""

import os

from nipype.interfaces.fsl.base import FSLCommand

from swane.config import dependency_policy
from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import GlobalPrefCategoryList
from swane.nipype_pipeline.MainWorkflow import MainWorkflow
from swane.resources import strings
from swane.utils.DependencyManager import (
    Dependence,
    DependenceStatus,
    DependencyManager,
)
from swane.utils.SubjectInputStateList import SubjectInputStateList


def _is_niimath(interface) -> bool:
    return os.path.basename(str(getattr(interface, "_cmd", ""))).startswith("niimath")


def test_default_engines_build_fsl_free_main_workflow(
    tmp_path, isolated_home, monkeypatch
):
    assert dependency_policy.FSL_MANDATORY is False
    monkeypatch.delenv("FSLDIR", raising=False)
    monkeypatch.delenv("FSLOUTPUTTYPE", raising=False)
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

    subject_dir = tmp_path / "subject"
    dicom_dir = subject_dir / "dicom"
    dicom_dir.mkdir(parents=True)
    global_config = ConfigManager(global_base_folder=str(tmp_path))
    global_config.set_main_working_directory(str(tmp_path))
    global_config.check_dependencies(dependency_manager)
    optional = global_config[GlobalPrefCategoryList.OPTIONAL_SERIES]
    for key in optional:
        optional[key] = "true"
    subject_config = ConfigManager(
        subject_folder=str(subject_dir), global_config=global_config
    )

    input_state_list = SubjectInputStateList(str(dicom_dir), global_config)
    for data_input in input_state_list:
        (dicom_dir / str(data_input)).mkdir()
        input_state_list[data_input].loaded = True
        input_state_list[data_input].volumes = (
            1 if data_input.value.max_volumes == 1 else 40
        )

    workflow = MainWorkflow(
        name="fsl_free",
        base_dir=str(subject_dir),
        global_config=global_config,
        subject_config=subject_config,
        dependency_manager=dependency_manager,
        subject_input_state_list=input_state_list,
        test_run=True,
    )
    nodes = workflow._get_all_nodes()
    names = {node.fullname for node in nodes}
    # Sanity: the analyses with an FSL alternative are actually in the graph.
    assert any(name.startswith("bundle_") for name in names)
    assert any(name.startswith("fmri_resting_state.") for name in names)

    fsl_nodes = sorted(
        "%s (%s)" % (node.fullname, type(node.interface).__name__)
        for node in nodes
        if (
            isinstance(node.interface, FSLCommand)
            or type(node.interface).__module__.startswith("nipype.interfaces.fsl")
        )
        and not _is_niimath(node.interface)
    )
    assert fsl_nodes == []

    niimath_output_types = {
        node.interface.inputs.output_type
        for node in nodes
        if _is_niimath(node.interface)
    }
    assert niimath_output_types == {"NIFTI_GZ"}
