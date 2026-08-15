"""Turn the cached phantom exam into a configured SWANe subject, per pass.

Each pass needs its own subject folder: it loads a different subset of inputs,
wires the venous series into a different shape, and carries its own
preferences. The DICOM itself is identical across passes, so the series folders
are **symlinked** rather than copied — the full exam is ~17k files and copying
it per pass would dominate the run.

The phantom folder names match ``DataInputList`` names one-to-one, with two
deliberate exceptions the catalog documents and the sweep exploits:

* ``venous_mr`` is a single 2-volume series (the "split it in time" path),
  while ``venous_mr_split_anat`` / ``venous_mr_split_angio`` carry the same two
  phases as separate 1-volume series (the "merge two series" path). Which pair
  gets wired onto ``VENOUS_MR`` / ``VENOUS_MR2`` is the ``venous_mr_shape`` axis;
* ``venous_ct``/``venous_ct2``/``venous_ct3`` are the non-contrast baseline plus
  the two one-sided opacifications, wired onto ``VENOUS_CT``/``2``/``3``
  according to the ``venous_ct_contrasts`` axis.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass

from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import GlobalPrefCategoryList
from swane.config.preference_list import TRACTS
from swane.utils.DataInputList import DataInputList as DIL
from swane.utils.SubjectInputStateList import SubjectInputStateList
from swane.tests.prerelease.plan import AXES_BY_NAME, GLOBAL, SHAPE, SUBJECT

DICOM_DIR_NAME = "dicom"

#: The tract the sweep exercises; every other XTRACT protocol is turned off so
#: a tractography pass stays to one bundle instead of twenty.
SWEEP_TRACT = "cst"


@dataclass
class PhantomExam:
    """The generated phantom, plus what its manifest says about each series."""

    root: str
    series: dict  # phantom folder name -> manifest entry

    @property
    def dicom_root(self) -> str:
        return os.path.join(self.root, DICOM_DIR_NAME)

    def folder(self, name: str) -> str:
        return os.path.join(self.dicom_root, name)

    def volumes(self, name: str) -> int:
        """Temporal volumes in a series, as SWANe counts them."""
        entry = self.series.get(name, {})
        if "n_vols" in entry:
            return int(entry["n_vols"])
        if "bvals" in entry:  # diffusion: one volume per b-value
            return len(entry["bvals"])
        return 1

    def dummy_volumes(self, name: str) -> tuple:
        entry = self.series.get(name, {})
        return int(entry.get("dummy_start", 0)), int(entry.get("dummy_end", 0))


def load_phantom(force: bool = False, cache_root: str = None) -> PhantomExam:
    """Build (or reuse) the phantom exam and read its manifest."""
    from swane.tests.helpers.phantom.dataset import get_phantom_subject

    root = get_phantom_subject(force=force, cache_root=cache_root)
    with open(os.path.join(root, "manifest.json")) as handle:
        manifest = json.load(handle)
    return PhantomExam(
        root=root, series={s["input"]: s for s in manifest.get("series", [])}
    )


def _link(source: str, dest: str) -> None:
    """Symlink a series folder, falling back to a copy where links are barred."""
    if os.path.lexists(dest):
        if os.path.islink(dest):
            os.unlink(dest)
        else:
            shutil.rmtree(dest)
    try:
        os.symlink(source, dest, target_is_directory=True)
    except (OSError, NotImplementedError):
        # Windows without developer mode, or a filesystem that refuses links.
        shutil.copytree(source, dest)


def _wiring(pass_item, exam: PhantomExam) -> dict:
    """Map ``DataInputList`` members to the phantom folders that feed them."""
    wiring = {}
    for data_input in pass_item.inputs:
        name = str(data_input)

        if data_input is DIL.VENOUS_MR:
            if pass_item.values.get("venous_mr_shape") == "two_series":
                # Two single-volume series: anatomic and angiographic apart.
                wiring[DIL.VENOUS_MR] = "venous_mr_split_anat"
                wiring[DIL.VENOUS_MR2] = "venous_mr_split_angio"
            else:
                # One 2-volume series; the workflow splits it in time.
                wiring[DIL.VENOUS_MR] = "venous_mr"
            continue

        if data_input is DIL.VENOUS_CT:
            # Baseline is mandatory; the workflow needs at least one contrast
            # phase and sums however many more it is given.
            wiring[DIL.VENOUS_CT] = "venous_ct"
            wiring[DIL.VENOUS_CT2] = "venous_ct2"
            if pass_item.values.get("venous_ct_contrasts") == "2":
                wiring[DIL.VENOUS_CT3] = "venous_ct3"
            continue

        wiring[data_input] = name

    missing = [
        folder for folder in wiring.values() if not os.path.isdir(exam.folder(folder))
    ]
    if missing:
        raise RuntimeError(
            "phantom is missing series %s; rebuild it with --rebuild-phantom"
            % ", ".join(sorted(missing))
        )
    return wiring


def _enable_optional_series(global_config: ConfigManager, wiring: dict) -> None:
    """Optional inputs default to *off*; a pass must opt every one it uses in.

    ``SubjectInputStateList`` silently drops optional inputs that are not
    enabled here, so forgetting this would produce a workflow quietly missing
    half the exam.
    """
    section = GlobalPrefCategoryList.OPTIONAL_SERIES
    for data_input in DIL:
        if not data_input.value.optional:
            continue
        name = data_input.value.name
        if name not in global_config[section]:
            continue
        wanted = data_input in wiring or any(
            other.value.parent_input == data_input.name for other in wiring
        )
        global_config[section][name] = "true" if wanted else "false"


def _apply_axis_values(pass_item, global_config, subject_config, exam, wiring) -> None:
    """Write the pass's axis values into the two configuration objects."""
    for axis_name, value in pass_item.values.items():
        axis = AXES_BY_NAME[axis_name]
        if axis.scope == GLOBAL:
            global_config[axis.section][axis.option] = str(value)
        elif axis.scope == SUBJECT:
            subject_config[str(axis.section)][axis.option] = str(value)
        elif axis.scope != SHAPE:
            raise ValueError("unknown axis scope %r" % axis.scope)

    # The dummy-volume axis is expressed against the phantom's own padding, so
    # trimming removes volumes that are genuinely identifiable in the data.
    if pass_item.values.get("fmri0_del_vols") == "trim":
        for data_input in (DIL.FMRI_0, DIL.FMRI_1):
            if data_input not in wiring:
                continue
            start, end = exam.dummy_volumes(str(data_input))
            subject_config[str(data_input)]["del_start_vols"] = str(start)
            subject_config[str(data_input)]["del_end_vols"] = str(end)

    # Keep tractography to the single tract the sweep is about.
    if pass_item.values.get("tractography") == "true":
        for tract in TRACTS:
            if tract in subject_config[str(DIL.DTI)]:
                subject_config[str(DIL.DTI)][tract] = (
                    "true" if tract == SWEEP_TRACT else "false"
                )


def prepare_subject(
    pass_item,
    exam: PhantomExam,
    work_dir: str,
    cores: int,
    ram_gb: float,
    slicer_path: str = "",
) -> tuple:
    """Create the subject folder for one pass and return its pieces.

    Returns
    -------
    (subject_dir, global_config, subject_config, input_state_list)
    """
    subject_dir = os.path.join(work_dir, pass_item.name)
    dicom_root = os.path.join(subject_dir, DICOM_DIR_NAME)
    os.makedirs(dicom_root, exist_ok=True)

    wiring = _wiring(pass_item, exam)
    for data_input, folder in wiring.items():
        _link(exam.folder(folder), os.path.join(dicom_root, str(data_input)))

    # nipype's FSCommand reads os.environ["SUBJECTS_DIR"] unconditionally as
    # soon as FreeSurfer is detected, and raises a bare KeyError when it is
    # unset (normally FreeSurferEnv.sh provides it). MainWorkflow points the
    # FreeSurfer workflow at the subject folder anyway, so use that here: it
    # satisfies nipype and keeps each pass's recon-all output isolated.
    os.environ["SUBJECTS_DIR"] = subject_dir

    # The global config lives in the subject folder too, so passes never share
    # (or corrupt) the developer's real ~/.swane settings.
    global_config = ConfigManager(global_base_folder=subject_dir)
    global_config.set_main_working_directory(work_dir)
    performance = GlobalPrefCategoryList.PERFORMANCE
    global_config[performance]["max_subj_cpu"] = str(cores)
    global_config[performance]["ram_gb"] = str(ram_gb)
    global_config[performance]["resource_monitor"] = "true"
    if slicer_path:
        global_config[GlobalPrefCategoryList.MAIN]["slicer_path"] = slicer_path

    _enable_optional_series(global_config, wiring)

    subject_config = ConfigManager(
        subject_folder=subject_dir, global_config=global_config
    )
    _apply_axis_values(pass_item, global_config, subject_config, exam, wiring)

    input_state_list = SubjectInputStateList(dicom_root, global_config)
    for data_input, folder in wiring.items():
        if data_input not in input_state_list:
            raise RuntimeError(
                "%s is not in the input list; its optional-series flag did not "
                "take effect" % data_input
            )
        input_state_list[data_input].loaded = True
        input_state_list[data_input].volumes = exam.volumes(folder)

    global_config.save()
    subject_config.save()
    return subject_dir, global_config, subject_config, input_state_list
