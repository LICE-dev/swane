from datetime import datetime
import os
from multiprocessing import cpu_count
from os.path import abspath

import swane_supplement
from swane.config.ConfigManager import ConfigManager
from swane.utils.SubjectInputStateList import SubjectInputStateList
from swane.utils.DataInputList import DataInputList as DIL, FMRI_NUM
from swane.config.config_enums import (
    PLANES,
    CORE_LIMIT,
    BLOCK_DESIGN,
    GlobalPrefCategoryList,
)
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.linear_reg_workflow import linear_reg_workflow
from swane.nipype_pipeline.workflows.task_fMRI_workflow import task_fMRI_workflow
from swane.nipype_pipeline.workflows.nonlinear_reg_workflow import (
    nonlinear_reg_workflow,
)
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow
from swane.nipype_pipeline.workflows.freesurfer_workflow import freesurfer_workflow
from swane.nipype_pipeline.workflows.flat1_workflow import flat1_workflow
from swane.nipype_pipeline.workflows.func_map_workflow import func_map_workflow
from swane.nipype_pipeline.workflows.venous_workflow import venous_workflow
from swane.nipype_pipeline.workflows.dti_preproc_workflow import dti_preproc_workflow
from swane.nipype_pipeline.workflows.tractography_workflow import (
    tractography_workflow,
    SIDES,
)
from swane.config.preference_list import TRACTS
from swane.utils.DependencyManager import DependencyManager
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import (
    MonitoredMultiProcPlugin,
)


DEBUG = False


# TODO implementazione error manager
class MainWorkflow(CustomWorkflow):
    Result_DIR: str = "results"

    is_resource_monitor: bool = False
    max_cpu: int = -1
    max_gpu: int = -1
    multicore_node_limit: CORE_LIMIT = CORE_LIMIT.SOFT_CAP

    name: str
    base_dir: str
    global_config: ConfigManager
    subject_config: ConfigManager
    dependency_manager: DependencyManager
    subject_input_state_list: SubjectInputStateList

    def __init__(
        self,
        name: str,
        base_dir: str,
        global_config: ConfigManager,
        subject_config: ConfigManager,
        dependency_manager: DependencyManager,
        subject_input_state_list: SubjectInputStateList,
    ):
        """
        Create the Workflows and their sub-workflows based on the list of available data inputs

        Parameters
        ----------
        name : str
        base_dir : str
        global_config : ConfigManager
            The app global configurations.
        subject_config : ConfigManager
            The subject specific configurations.
        dependency_manager: DependencyManager
            The state of application dependency
        subject_input_state_list : SubjectInputStateList
            The list of all available input data from the DICOM directory.

        """

        super().__init__(name, base_dir)

        self.global_config = global_config
        self.subject_config = subject_config
        self.dependency_manager = dependency_manager
        self.subject_input_state_list = subject_input_state_list

        if not subject_input_state_list.is_ref_loaded:
            return

        self.set_resources_configuration()
        self.set_analyses_request()

        self.launch_3dt1_analysis()
        self.launch_ai_analysis()
        self.launch_freesurfer_analysis()
        self.launch_3dflair_analysis()
        self.launch_flat1_analysis()
        self.launch_2dflair_analysis()
        self.launch_t2cor_analysis()
        self.launch_mdc_analysis()
        self.launch_asl_analysis()
        self.launch_pet_analysis()
        self.launch_venous_analysis()
        self.launch_dti_analysis()
        self.launch_fMRI_analysis()

        # Remove reference to original variables to prevent crash during subprocess spawn in MacOS
        # Maybe this can be solved setting fork subprocess method too
        self.global_config = None
        self.subject_config = None
        self.dependency_manager = None
        self.subject_input_state_list = None

    def set_resources_configuration(self):
        # CPU cores and memory management
        self.is_resource_monitor = self.global_config.getboolean_safe(
            GlobalPrefCategoryList.PERFORMANCE, "resource_monitor"
        )
        self.max_cpu = self.global_config.getint_safe(
            GlobalPrefCategoryList.PERFORMANCE, "max_subj_cu"
        )
        if self.max_cpu < 1:
            self.max_cpu = cpu_count()
        self.multicore_node_limit = self.global_config.getenum_safe(
            GlobalPrefCategoryList.PERFORMANCE, "multicore_node_limit"
        )
        # GPU management
        self.max_gpu = self.global_config.getint_safe(
            GlobalPrefCategoryList.PERFORMANCE, "max_subj_gpu"
        )
        if self.max_gpu < 0:
            self.max_gpu = MonitoredMultiProcPlugin.gpu_count()

        try:
            if not self.dependency_manager.is_cuda():
                self.subject_config[DIL.DTI]["cuda"] = "false"
            else:
                self.subject_config[DIL.DTI]["cuda"] = self.global_config[
                    GlobalPrefCategoryList.PERFORMANCE
                ]["cuda"]
        except:
            self.subject_config[DIL.DTI]["cuda"] = "false"

        self.subject_config.sections()

        # TODO - NOT USED, WHY?
        max_node_cpu = max(int(self.max_cpu / 2), 1)

    def set_analyses_request(self):
        # Check for FreeSurfer requirement and request
        self.is_freesurfer = (
            self.dependency_manager.is_freesurfer()
            and self.subject_config.get_workflow_freesurfer_pref()
        )
        self.is_hippo_amyg_labels = (
            self.dependency_manager.is_freesurfer_matlab()
            and self.subject_config.get_workflow_hippo_pref()
        )

        # Check for FLAT1 requirement and request
        self.is_flat1 = (
            self.subject_config.getboolean_safe(DIL.T13D, "flat1")
            and self.subject_input_state_list[DIL.FLAIR3D].loaded
        )
        # Check for Asymmetry Index request
        self.is_ai = (
            self.subject_config.getboolean_safe(DIL.PET, "ai")
            and self.subject_input_state_list[DIL.PET].loaded
        ) or (
            self.subject_config.getboolean_safe(DIL.ASL, "ai")
            and self.subject_input_state_list[DIL.ASL].loaded
        )
        # Check for Tractography request
        self.is_tractography = self.subject_config.getboolean_safe(
            DIL.DTI, "tractography"
        )

    def launch_3dt1_analysis(self):
        ref_dir = self.subject_input_state_list.get_dicom_dir(DIL.T13D)
        self.t1 = ref_workflow(
            name=DIL.T13D.value.workflow_name,
            dicom_dir=ref_dir,
            config=self.subject_config[DIL.T13D],
        )
        self.t1.long_name = "3D T1w analysis"
        self.add_nodes([self.t1])

        self.t1.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="ref",
            sub_folder=self.Result_DIR,
        )
        self.t1.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="ref_brain",
            sub_folder=self.Result_DIR,
        )

    def launch_ai_analysis(self):
        if not self.is_ai:
            return

        # Non linear registration for Asymmetry Index
        self.sym = nonlinear_reg_workflow(name="sym")
        self.sym.long_name = "Symmetric atlas registration"

        sym_inputnode = self.sym.get_node("inputnode")
        sym_template = swane_supplement.sym_template
        sym_inputnode.inputs.atlas = sym_template
        self.connect(self.t1, "outputnode.ref_brain", self.sym, "inputnode.in_file")

    def launch_freesurfer_analysis(self):
        if not self.is_freesurfer:
            return

        # FreeSurfer analysis
        self.freesurfer = freesurfer_workflow(
            name="freesurfer",
            is_hippo_amyg_labels=self.is_hippo_amyg_labels,
            max_cpu=self.max_cpu,
            multicore_node_limit=self.multicore_node_limit,
        )
        self.freesurfer.long_name = "Freesurfer analysis"

        freesurfer_inputnode = self.freesurfer.get_node("inputnode")
        freesurfer_inputnode.inputs.subjects_dir = self.base_dir
        self.connect(self.t1, "outputnode.ref", self.freesurfer, "inputnode.ref")

        self.freesurfer.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="pial",
            sub_folder=self.Result_DIR,
        )
        self.freesurfer.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="white",
            sub_folder=self.Result_DIR,
        )
        self.freesurfer.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="vol_label_file",
            sub_folder=self.Result_DIR,
        )
        if self.is_hippo_amyg_labels:
            regex_subs = [("-T1.*.mgz", ".mgz")]
            self.freesurfer.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="lh_hippoAmygLabels",
                sub_folder="scene.segmentHA",
                regexp_substitutions=regex_subs,
            )
            self.freesurfer.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="rh_hippoAmygLabels",
                sub_folder="scene.segmentHA",
                regexp_substitutions=regex_subs,
            )

    def launch_3dflair_analysis(self):
        if not self.subject_input_state_list[DIL.FLAIR3D].loaded:
            return

        # 3D Flair analysis
        flair_dir = self.subject_input_state_list.get_dicom_dir(DIL.FLAIR3D)
        self.flair = linear_reg_workflow(
            name=DIL.FLAIR3D.value.workflow_name,
            dicom_dir=flair_dir,
            config=self.subject_config[DIL.FLAIR3D],
        )
        self.flair.long_name = "3D Flair analysis"
        self.add_nodes([self.flair])

        flair_inputnode = self.flair.get_node("inputnode")
        flair_inputnode.inputs.output_name = "flair"
        self.connect(self.t1, "outputnode.ref_brain", self.flair, "inputnode.reference")

        self.flair.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="registered_file",
            sub_folder=self.Result_DIR,
        )

        self.flair.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="betted_registered_file",
            sub_folder=self.Result_DIR,
        )

        # TODO: explore possibility of freesurfer based asymmetry index
        # if is_freesurfer:
        #     from swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow import freesurfer_asymmetry_index_workflow
        #     flair_ai = freesurfer_asymmetry_index_workflow(name="flair_ai")
        #     self.connect(flair, "outputnode.registered_file", flair_ai, "inputnode.in_file")
        #     self.connect(freesurfer, "outputnode.vol_label_file_nii", flair_ai, "inputnode.seg_file")

    def launch_flat1_analysis(self):
        if not self.is_flat1:
            return

        # Non linear registration to MNI1mm Atlas for FLAT1
        self.mni1 = nonlinear_reg_workflow(name="mni1")
        self.mni1.long_name = "MNI atlas registration"

        mni1_inputnode = self.mni1.get_node("inputnode")
        mni1_path = abspath(
            os.path.join(
                os.environ["FSLDIR"], "data/standard/MNI152_T1_1mm_brain.nii.gz"
            )
        )
        mni1_inputnode.inputs.atlas = mni1_path
        self.connect(self.t1, "outputnode.ref_brain", self.mni1, "inputnode.in_file")

        # FLAT1 analysis
        self.flat1 = flat1_workflow(name="FLAT1", mni1_dir=mni1_path)
        self.flat1.long_name = "FLAT1 analysis"

        self.connect(self.t1, "outputnode.ref_brain", self.flat1, "inputnode.ref_brain")
        self.connect(
            self.flair,
            "outputnode.registered_file",
            self.flat1,
            "inputnode.flair_brain",
        )
        self.connect(
            self.mni1,
            "outputnode.fieldcoeff_file",
            self.flat1,
            "inputnode.ref_2_mni1_warp",
        )
        self.connect(
            self.mni1,
            "outputnode.inverse_warp",
            self.flat1,
            "inputnode.ref_2_mni1_inverse_warp",
        )

        self.flat1.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="extension_z",
            sub_folder=self.Result_DIR,
        )
        self.flat1.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="junction_z",
            sub_folder=self.Result_DIR,
        )
        self.flat1.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="binary_flair",
            sub_folder=self.Result_DIR,
        )

    def launch_2dflair_analysis(self):
        for plane in PLANES:
            if (
                DIL["FLAIR2D_%s" % plane.name] in self.subject_input_state_list
                and self.subject_input_state_list[DIL["FLAIR2D_%s" % plane.name]].loaded
            ):
                flair_dir = self.subject_input_state_list.get_dicom_dir(
                    DIL["FLAIR2D_%s" % plane.name]
                )
                self.flair2d = linear_reg_workflow(
                    name=DIL["FLAIR2D_%s" % plane.name].value.workflow_name,
                    dicom_dir=flair_dir,
                    config=None,
                    is_volumetric=False,
                )
                self.flair2d.long_name = "2D %s FLAIR analysis" % plane.value
                self.add_nodes([self.flair2d])

                flair2d_inputnode = self.flair2d.get_node("inputnode")
                flair2d_inputnode.inputs.crop = False
                flair2d_inputnode.inputs.output_name = (
                    "flair2d_%s" % plane
                )
                self.connect(
                    self.t1, "outputnode.ref_brain", self.flair2d, "inputnode.reference"
                )

                self.flair2d.sink_result(
                    save_path=self.base_dir,
                    result_node="outputnode",
                    result_name="betted_registered_file",
                    sub_folder=self.Result_DIR,
                )

    def launch_t2cor_analysis(self):
        if (
            not DIL.T2_COR in self.subject_input_state_list
            or not self.subject_input_state_list[DIL.T2_COR].loaded
        ):
            return

        t2_cor_dir = self.subject_input_state_list.get_dicom_dir(DIL.T2_COR)
        self.t2_cor = linear_reg_workflow(
            name=DIL.T2_COR.value.workflow_name,
            dicom_dir=t2_cor_dir,
            config=None,
            is_volumetric=False,
            is_partial_coverage=True
        )
        self.t2_cor.long_name = "2D coronal T2 analysis"
        self.add_nodes([self.t2_cor])

        t2_cor_inputnode = self.t2_cor.get_node("inputnode")
        t2_cor_inputnode.inputs.crop = False
        t2_cor_inputnode.inputs.output_name = "t2_cor"
        self.connect(self.t1, "outputnode.ref", self.t2_cor, "inputnode.reference")
        self.connect(self.t1, "outputnode.ref_mask", self.t2_cor, "inputnode.brain_mask")

        self.t2_cor.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="registered_file",
            sub_folder=self.Result_DIR,
        )

        self.t2_cor.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="betted_registered_file",
            sub_folder=self.Result_DIR,
        )

    def launch_mdc_analysis(self):
        if not self.subject_input_state_list[DIL.MDC].loaded:
            return

        # MDC analysis
        mdc_dir = self.subject_input_state_list.get_dicom_dir(DIL.MDC)
        self.mdc = linear_reg_workflow(
            name=DIL.MDC.value.workflow_name,
            dicom_dir=mdc_dir,
            config=self.subject_config[DIL.MDC],
        )
        self.mdc.long_name = "Post-contrast 3D T1w analysis"
        self.add_nodes([self.mdc])

        mdc_inputnode = self.mdc.get_node("inputnode")
        mdc_inputnode.inputs.crop = True
        mdc_inputnode.inputs.output_name = "mdc"
        self.connect(self.t1, "outputnode.ref_brain", self.mdc, "inputnode.reference")

        self.mdc.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="registered_file",
            sub_folder=self.Result_DIR,
        )

        self.mdc.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="betted_registered_file",
            sub_folder=self.Result_DIR,
        )

    def launch_asl_analysis(self):
        if not self.subject_input_state_list[DIL.ASL].loaded:
            return

        # ASL analysis
        asl_dir = self.subject_input_state_list.get_dicom_dir(DIL.ASL)
        self.asl = func_map_workflow(
            name=DIL.ASL.value.workflow_name,
            dicom_dir=asl_dir,
            is_freesurfer=self.is_freesurfer,
            config=self.subject_config[DIL.ASL],
        )
        self.asl.long_name = "Arterial Spin Labelling analysis"

        self.connect(self.t1, "outputnode.ref_brain", self.asl, "inputnode.reference")
        self.connect(self.t1, "outputnode.ref_mask", self.asl, "inputnode.brain_mask")

        self.asl.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="registered_file",
            sub_folder=self.Result_DIR,
        )

        if self.is_freesurfer:
            self.connect(
                self.freesurfer,
                "outputnode.subjects_dir",
                self.asl,
                "inputnode.freesurfer_subjects_dir",
            )
            self.connect(
                self.freesurfer,
                "outputnode.subject_id",
                self.asl,
                "inputnode.freesurfer_subject_id",
            )
            self.connect(
                self.freesurfer, "outputnode.bgROI", self.asl, "inputnode.bgROI"
            )

            self.asl.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="surf_lh",
                sub_folder=self.Result_DIR,
            )
            self.asl.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="surf_rh",
                sub_folder=self.Result_DIR,
            )
            self.asl.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="zscore",
                sub_folder=self.Result_DIR,
            )
            self.asl.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="zscore_surf_lh",
                sub_folder=self.Result_DIR,
            )
            self.asl.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="zscore_surf_rh",
                sub_folder=self.Result_DIR,
            )

        if self.subject_config.getboolean_safe(DIL.ASL, "ai"):
            self.connect(
                self.sym,
                "outputnode.fieldcoeff_file",
                self.asl,
                "inputnode.ref_2_sym_warp",
            )
            self.connect(
                self.sym,
                "outputnode.inverse_warp",
                self.asl,
                "inputnode.ref_2_sym_invwarp",
            )

            self.asl.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="ai",
                sub_folder=self.Result_DIR,
            )

            if self.is_freesurfer:
                self.asl.sink_result(
                    save_path=self.base_dir,
                    result_node="outputnode",
                    result_name="ai_surf_lh",
                    sub_folder=self.Result_DIR,
                )
                self.asl.sink_result(
                    save_path=self.base_dir,
                    result_node="outputnode",
                    result_name="ai_surf_rh",
                    sub_folder=self.Result_DIR,
                )

    def launch_pet_analysis(self):
        if not self.subject_input_state_list[
            DIL.PET
        ].loaded:  # and check_input['ct_brain']:
            return

        # PET analysis
        pet_dir = self.subject_input_state_list.get_dicom_dir(DIL.PET)
        self.pet = func_map_workflow(
            name=DIL.PET.value.workflow_name,
            dicom_dir=pet_dir,
            is_freesurfer=self.is_freesurfer,
            config=self.subject_config[DIL.PET],
        )
        self.pet.long_name = "Pet analysis"

        self.connect(self.t1, "outputnode.ref", self.pet, "inputnode.reference")
        self.connect(self.t1, "outputnode.ref_mask", self.pet, "inputnode.brain_mask")

        self.pet.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="registered_file",
            sub_folder=self.Result_DIR,
        )

        if self.is_freesurfer:
            self.connect(
                self.freesurfer,
                "outputnode.subjects_dir",
                self.pet,
                "inputnode.freesurfer_subjects_dir",
            )
            self.connect(
                self.freesurfer,
                "outputnode.subject_id",
                self.pet,
                "inputnode.freesurfer_subject_id",
            )
            self.connect(
                self.freesurfer, "outputnode.bgROI", self.pet, "inputnode.bgROI"
            )

            self.pet.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="surf_lh",
                sub_folder=self.Result_DIR,
            )
            self.pet.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="surf_rh",
                sub_folder=self.Result_DIR,
            )
            self.pet.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="zscore",
                sub_folder=self.Result_DIR,
            )
            self.pet.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="zscore_surf_lh",
                sub_folder=self.Result_DIR,
            )
            self.pet.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="zscore_surf_rh",
                sub_folder=self.Result_DIR,
            )

            # TODO work in progress for segmentation based asymmetry study
            # from swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow import freesurfer_asymmetry_index_workflow
            # pet_ai = freesurfer_asymmetry_index_workflow(name="pet_ai")
            # self.connect(pet, "outputnode.registered_file", pet_ai, "inputnode.in_file")
            # self.connect(freesurfer, "outputnode.vol_label_file_nii", pet_ai, "inputnode.seg_file")

        if self.subject_config.getboolean_safe(DIL.PET, "ai"):
            self.connect(
                self.sym,
                "outputnode.fieldcoeff_file",
                self.pet,
                "inputnode.ref_2_sym_warp",
            )
            self.connect(
                self.sym,
                "outputnode.inverse_warp",
                self.pet,
                "inputnode.ref_2_sym_invwarp",
            )

            self.pet.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="ai",
                sub_folder=self.Result_DIR,
            )

            if self.is_freesurfer:
                self.pet.sink_result(
                    save_path=self.base_dir,
                    result_node="outputnode",
                    result_name="ai_surf_lh",
                    sub_folder=self.Result_DIR,
                )
                self.pet.sink_result(
                    save_path=self.base_dir,
                    result_node="outputnode",
                    result_name="ai_surf_rh",
                    sub_folder=self.Result_DIR,
                )

    def launch_venous_analysis(self):
        if (
            not self.subject_input_state_list[DIL.VENOUS].loaded
            or not self.subject_input_state_list[DIL.VENOUS].volumes
            + self.subject_input_state_list[DIL.VENOUS2].volumes
            == 2
        ):
            return

        # Venous analysis
        venous_dir = self.subject_input_state_list.get_dicom_dir(DIL.VENOUS)
        venous2_dir = None
        if self.subject_input_state_list[DIL.VENOUS2].loaded:
            venous2_dir = self.subject_input_state_list.get_dicom_dir(DIL.VENOUS2)
        self.venous = venous_workflow(
            DIL.VENOUS.value.workflow_name,
            venous_dir,
            self.subject_config[DIL.VENOUS],
            venous2_dir,
        )
        self.venous.long_name = "Venous MRA analysis"

        self.connect(
            self.t1, "outputnode.ref_brain", self.venous, "inputnode.ref_brain"
        )

        self.venous.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="veins",
            sub_folder=self.Result_DIR,
        )

    def launch_dti_analysis(self):
        if not self.subject_input_state_list[DIL.DTI].loaded:
            return

        # DTI analysis
        dti_dir = self.subject_input_state_list.get_dicom_dir(DIL.DTI)
        mni_dir = abspath(
            os.path.join(
                os.environ["FSLDIR"], "data/standard/MNI152_T1_2mm_brain.nii.gz"
            )
        )

        self.dti_preproc = dti_preproc_workflow(
            name=DIL.DTI.value.workflow_name,
            dti_dir=dti_dir,
            config=self.subject_config[DIL.DTI],
            mni_dir=mni_dir,
            max_cpu=self.max_cpu,
            multicore_node_limit=self.multicore_node_limit,
        )
        self.dti_preproc.long_name = "Diffusion Tensor Imaging preprocessing"
        self.connect(
            self.t1, "outputnode.ref_brain", self.dti_preproc, "inputnode.ref_brain"
        )

        self.dti_preproc.sink_result(
            save_path=self.base_dir,
            result_node="outputnode",
            result_name="FA",
            sub_folder=self.Result_DIR,
        )

        if self.is_tractography:
            for tract in TRACTS.keys():
                try:
                    if not self.subject_config.getboolean_safe(DIL.DTI, tract):
                        continue
                except:
                    continue

                tract_workflow = tractography_workflow(
                    tract, self.subject_config[DIL.DTI]
                )
                if tract_workflow is not None:
                    tract_workflow.long_name = TRACTS[tract][0] + " tractography"
                    self.connect(
                        self.dti_preproc,
                        "outputnode.fsamples",
                        tract_workflow,
                        "inputnode.fsamples",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.nodiff_mask_file",
                        tract_workflow,
                        "inputnode.mask",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.phsamples",
                        tract_workflow,
                        "inputnode.phsamples",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.thsamples",
                        tract_workflow,
                        "inputnode.thsamples",
                    )
                    self.connect(
                        self.t1,
                        "outputnode.ref_brain",
                        tract_workflow,
                        "inputnode.ref_brain",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.diff2ref_mat",
                        tract_workflow,
                        "inputnode.diff2ref_mat",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.ref2diff_mat",
                        tract_workflow,
                        "inputnode.ref2diff_mat",
                    )
                    self.connect(
                        self.dti_preproc,
                        "outputnode.mni2ref_warp",
                        tract_workflow,
                        "inputnode.mni2ref_warp",
                    )

                    for side in SIDES:
                        tract_workflow.sink_result(
                            save_path=self.base_dir,
                            result_node="outputnode",
                            result_name="waytotal_%s" % side,
                            sub_folder=self.Result_DIR + ".dti",
                        )
                        tract_workflow.sink_result(
                            save_path=self.base_dir,
                            result_node="outputnode",
                            result_name="fdt_paths_%s" % side,
                            sub_folder=self.Result_DIR + ".dti",
                        )

    def launch_fMRI_analysis(self):
        # Check for Task FMRI sequences
        for y in range(FMRI_NUM):

            if not self.subject_input_state_list[DIL["FMRI_%d" % y]].loaded:
                continue

            dicom_dir = self.subject_input_state_list.get_dicom_dir(DIL["FMRI_%d" % y])
            self.fMRI = task_fMRI_workflow(
                name=DIL["FMRI_%d" % y].value.workflow_name,
                dicom_dir=dicom_dir,
                config=self.subject_config[DIL["FMRI_%d" % y]],
                base_dir=self.base_dir,
            )
            self.fMRI.long_name = "Task fMRI analysis - %d" % y
            self.connect(
                self.t1, "outputnode.ref_brain", self.fMRI, "inputnode.ref_BET"
            )
            self.fMRI.sink_result(
                save_path=self.base_dir,
                result_node="outputnode",
                result_name="threshold_file_1",
                sub_folder=self.Result_DIR + ".fMRI",
            )
            if (
                self.subject_config.getenum_safe(DIL["FMRI_%d" % y], "block_design")
                == BLOCK_DESIGN.RARB
            ):
                self.fMRI.sink_result(
                    save_path=self.base_dir,
                    result_node="outputnode",
                    result_name="threshold_file_2",
                    sub_folder=self.Result_DIR + ".fMRI",
                )
