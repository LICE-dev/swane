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


def _build_main_workflow(
    tmp_path, monkeypatch, main_dir=None, subject_name="subject", configure=None
):
    """Build the default-engine MainWorkflow with every input loaded, FSL
    missing. ``configure(global_config, subject_config)`` may tune the
    preferences before the graph is built."""
    assert dependency_policy.FSL_MANDATORY is False
    main_dir = main_dir or tmp_path
    monkeypatch.delenv("FSLDIR", raising=False)
    monkeypatch.delenv("FSLOUTPUTTYPE", raising=False)
    monkeypatch.setenv("SUBJECTS_DIR", str(main_dir))
    monkeypatch.setattr(
        DependencyManager,
        "check_fsl",
        staticmethod(
            lambda: Dependence(DependenceStatus.MISSING, strings.check_dep_fsl_error)
        ),
    )
    dependency_manager = DependencyManager()
    assert not dependency_manager.is_fsl()

    subject_dir = main_dir / subject_name
    dicom_dir = subject_dir / "dicom"
    dicom_dir.mkdir(parents=True)
    global_config = ConfigManager(global_base_folder=str(tmp_path))
    global_config.set_main_working_directory(str(main_dir))
    global_config.check_dependencies(dependency_manager)
    optional = global_config[GlobalPrefCategoryList.OPTIONAL_SERIES]
    for key in optional:
        optional[key] = "true"
    subject_config = ConfigManager(
        subject_folder=str(subject_dir), global_config=global_config
    )
    if configure is not None:
        configure(global_config, subject_config)

    input_state_list = SubjectInputStateList(str(dicom_dir), global_config)
    for data_input in input_state_list:
        (dicom_dir / str(data_input)).mkdir()
        input_state_list[data_input].loaded = True
        input_state_list[data_input].volumes = (
            1 if data_input.value.max_volumes == 1 else 40
        )

    return MainWorkflow(
        name="fsl_free",
        base_dir=str(subject_dir),
        global_config=global_config,
        subject_config=subject_config,
        dependency_manager=dependency_manager,
        subject_input_state_list=input_state_list,
        test_run=True,
    )


def test_default_engines_build_fsl_free_main_workflow(
    tmp_path, isolated_home, monkeypatch
):
    workflow = _build_main_workflow(tmp_path, monkeypatch)
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


# --- blank spaces in the subject path on Windows --------------------------------
#
# On Windows SWANe allows blank spaces in the main working directory and in the
# subject folder. That is only safe if every command line a Windows workflow can
# run keeps each path in one argument. The graph is built under simulated
# Windows (SWANe's quoting proxy installed in Nipype's CommandLine core, the
# Windows helpers answering True) with blank spaces in the main working
# directory, the subject folder, the node working directory and the 3D Slicer
# install path. Values only known at run time (connected inputs) are filled with
# representative fakes: path inputs with real files under the spaced subject
# folder (a tiny NIfTI, since some interfaces read their input while building the
# command line); numbers with 1.5/1; inputs fed through a connection function
# (op_string builders) by evaluating that function on a representative source
# value. Each command line is then split with the MSVCRT rules cmd.exe hands to
# the tools, and every path must come back as one intact argument.

MAIN_DIR = "MAINA MAINB"
SUBJECT_DIR = "SUBJA SUBJB"
SLICER_DIR = "SLICERA SLICERB"
WORK_DIR = "WORKA WORKB"
_SPACED_NAMES = (MAIN_DIR, SUBJECT_DIR, SLICER_DIR, WORK_DIR)


def _path_kind(trait):
    """Return "file", "dir", "list" (of paths) or None for an input trait."""
    from nipype.interfaces.base import traits
    from nipype.interfaces.base.traits_extension import BasePath, Directory

    if trait.is_trait_type(Directory):
        return "dir"
    if trait.is_trait_type(BasePath):
        return "file"
    if trait.is_trait_type(traits.List):
        inner = getattr(trait, "inner_traits", None) or ()
        if any(t.is_trait_type(BasePath) for t in inner):
            return "list"
    return None


def _fake_value(name, trait, fake_dir, make_nifti):
    from nipype.interfaces.base import traits

    kind = _path_kind(trait)
    if kind == "dir":
        path = fake_dir / ("%s dir" % name)
        path.mkdir(exist_ok=True)
        return str(path)
    if kind == "file":
        return make_nifti("%s file.nii.gz" % name)
    if kind == "list":
        return [make_nifti("%s file.nii.gz" % name)]
    if trait.is_trait_type(traits.Float):
        return 1.5
    if trait.is_trait_type(traits.Int):
        return 1
    if trait.is_trait_type(traits.Bool):
        return True
    raise AssertionError("no representative value for input %r (%s)" % (name, trait))


def _set_from_connect_function(inputs, dest, source, fake_path):
    """Set ``dest`` from a ``(output, function_source, args)`` connection
    evaluated on a representative source value: path lists/paths for path
    inputs, a ``[number, path]`` Merge output (the high-pass builder) or a
    plain number for the others. The first candidate the function and the
    input trait both accept wins."""
    from nipype.pipeline.engine.utils import evaluate_connect_function
    from traits.api import TraitError

    _, function_source, args = source
    if _path_kind(inputs.trait(dest)):
        candidates = ([fake_path] * 10, fake_path)
    else:
        candidates = ([1.5, fake_path], 1.5)
    for first_arg in candidates:
        try:
            value = evaluate_connect_function(function_source, args, first_arg)
            setattr(inputs, dest, value)
            return
        except (TypeError, IndexError, TraitError):
            continue
    raise AssertionError("cannot evaluate connection function %s" % function_source)


def _broken_paths(cmdline, paths):
    """Return the paths of ``cmdline`` that do not survive a Windows split."""
    from swane.patches.windows_compat import windows_split

    tokens = windows_split(cmdline)
    broken = [path for path in paths if path not in tokens]
    # No token may carry half of a spaced folder name: that would be a path
    # broken in two by an unquoted blank space.
    for spaced in _SPACED_NAMES:
        for half in spaced.split(" "):
            broken += [t for t in tokens if half in t and spaced not in t]
    return broken


def test_windows_command_lines_keep_spaced_paths_intact(
    tmp_path, isolated_home, monkeypatch
):
    import nibabel as nib
    import numpy as np
    from nipype.interfaces.base import CommandLine, core as nipype_core, isdefined
    from nipype.pipeline.engine import MapNode

    import swane.patches.nipype_patches as nipype_patches
    import swane.utils.platform_and_tools_utils as platform_utils
    from swane.config.config_enums import SliceTiming
    from swane.patches import windows_compat
    from swane.utils.DataInputList import DataInputList

    # Simulated Windows: the quoting proxy, the cmdline helpers and the
    # platform helper all answer as on Windows.
    monkeypatch.setattr(windows_compat, "is_windows", lambda: True)
    monkeypatch.setattr(platform_utils, "is_windows", lambda: True)
    monkeypatch.setattr(nipype_core, "shlex", nipype_core.shlex)
    assert nipype_patches.install_windows_cmdline_quoting() is True

    main_dir = tmp_path / MAIN_DIR
    main_dir.mkdir()
    slicer = tmp_path / SLICER_DIR / "Slicer.exe"
    slicer.parent.mkdir()
    slicer.write_text("")
    monkeypatch.setattr(DependencyManager, "is_slicer", staticmethod(lambda c: True))

    def configure(global_config, subject_config):
        # Reach the optional command-line nodes too: FLAT1, slice timing
        # correction and the 3D Slicer scalp removal of the venous CT.
        global_config[GlobalPrefCategoryList.MAIN]["slicer_path"] = str(slicer)
        subject_config[DataInputList.T13D]["flat1"] = "true"
        for data_input in DataInputList:
            if data_input.name.startswith("FMRI_"):
                subject_config[data_input]["slice_timing"] = SliceTiming.UP.name

    workflow = _build_main_workflow(
        tmp_path,
        monkeypatch,
        main_dir=main_dir,
        subject_name=SUBJECT_DIR,
        configure=configure,
    )

    fake_dir = main_dir / SUBJECT_DIR / "fake inputs"
    fake_dir.mkdir()
    work_dir = main_dir / SUBJECT_DIR / WORK_DIR
    work_dir.mkdir()
    # Generated output names (genfile) resolve against the node working dir.
    monkeypatch.chdir(work_dir)
    image = nib.Nifti1Image(np.zeros((4, 4, 3, 2), np.float32), np.eye(4))

    def make_nifti(file_name):
        path = fake_dir / file_name
        if not path.exists():
            nib.save(image, str(path))
        return str(path)

    graph = workflow._create_flat_graph()
    checked = {}
    failures = {}
    for node in graph.nodes():
        interface = node.interface
        if not isinstance(interface, CommandLine):
            continue
        inputs = interface.inputs
        if isinstance(node, MapNode):
            # A MapNode keeps its own inputs: run one iteration's worth.
            for name in node.inputs.copyable_trait_names():
                value = getattr(node.inputs, name)
                if isdefined(value):
                    if name in node.iterfield:
                        value = value[0]
                    setattr(inputs, name, value)
        for _, _, data in graph.in_edges(node, data=True):
            for source, dest in data["connect"]:
                if isinstance(source, tuple):
                    fake_path = make_nifti("%s source.nii.gz" % dest)
                    _set_from_connect_function(inputs, dest, source, fake_path)
                else:
                    value = _fake_value(dest, inputs.trait(dest), fake_dir, make_nifti)
                    setattr(inputs, dest, value)
        for name in inputs.copyable_trait_names():
            trait = inputs.trait(name)
            xor_defined = any(isdefined(getattr(inputs, x)) for x in trait.xor or ())
            if (
                trait.mandatory
                and not xor_defined
                and not isdefined(getattr(inputs, name))
            ):
                setattr(inputs, name, _fake_value(name, trait, fake_dir, make_nifti))

        cmdline = interface.cmdline
        paths = []
        for name in inputs.copyable_trait_names():
            value = getattr(inputs, name)
            kind = _path_kind(inputs.trait(name))
            if kind is None or not isdefined(value):
                continue
            values = value if kind == "list" else [value]
            # Inputs without argstr (e.g. slicer_cmd) only count when the
            # interface writes them into the command line itself.
            if inputs.trait(name).argstr or str(values[0]) in cmdline:
                paths.extend(str(v) for v in values)
        broken = _broken_paths(cmdline, paths)
        if broken:
            failures[node.fullname] = (cmdline, broken)
        checked[node.fullname] = type(interface).__name__

    assert sorted(failures) == [], failures

    kinds = set(checked.values())
    # Sanity: the command-line interfaces a Windows workflow runs were reached.
    assert {
        "CustomDcm2niix",
        "ImageMaths",
        "ApplyMask",
        "BinaryMaths",
        "NiiMathRobustFov",
        "NiiMathSliceTimer",
        "SegmentEndocranium",
        "SpatialFilter",
        "ThrROI",
    } <= kinds, kinds
    # The high-pass filters embed the mean image path in their op_string.
    assert any(name.endswith("highpass_clean") for name in checked)
