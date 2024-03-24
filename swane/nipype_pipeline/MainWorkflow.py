import os
from multiprocessing import cpu_count
from os.path import abspath

import swane_supplement
from swane.config.ConfigManager import ConfigManager
from swane.utils.SubjectInputStateList import SubjectInputStateList
from swane.utils.DataInputList import DataInputList as DIL, FMRI_NUM
from swane.config.config_enums import PLANES, CORE_LIMIT, BLOCK_DESIGN, GlobalPrefCategoryList
from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow
from swane.nipype_pipeline.workflows.linear_reg_workflow import linear_reg_workflow
from swane.nipype_pipeline.workflows.task_fMRI_workflow import task_fMRI_workflow
from swane.nipype_pipeline.workflows.nonlinear_reg_workflow import nonlinear_reg_workflow
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow
from swane.nipype_pipeline.workflows.freesurfer_workflow import freesurfer_workflow
from swane.nipype_pipeline.workflows.flat1_workflow import flat1_workflow
from swane.nipype_pipeline.workflows.func_map_workflow import func_map_workflow
from swane.nipype_pipeline.workflows.venous_workflow import venous_workflow
from swane.nipype_pipeline.workflows.dti_preproc_workflow import dti_preproc_workflow
from swane.nipype_pipeline.workflows.tractography_workflow import tractography_workflow, SIDES
from swane.config.preference_list import TRACTS
from swane.utils.DependencyManager import DependencyManager
from swane.nipype_pipeline.engine.MonitoredMultiProcPlugin import MonitoredMultiProcPlugin


DEBUG = False


# TODO implementazione error manager
class MainWorkflow(CustomWorkflow):
    Result_DIR = 'results'

    def __init__(self, name: str, base_dir: str):
        super().__init__(name, base_dir)
        self.is_resource_monitor: bool = False
        self.max_cpu: int = -1
        self.max_gpu: int = -1
        self.multicore_node_limit: CORE_LIMIT = CORE_LIMIT.SOFT_CAP

    def add_input_folders(self, global_config: ConfigManager, subject_config: ConfigManager,
                          dependency_manager: DependencyManager, subject_input_state_list: SubjectInputStateList):
        """
        Create the Workflows and their sub-workflows based on the list of available data inputs 

        Parameters
        ----------
        global_config : ConfigManager
            The app global configurations.
        subject_config : ConfigManager
            The subject specific configurations.
        dependency_manager: DependencyManager
            The state of application dependency
        subject_input_state_list : SubjectInputStateList
            The list of all available input data from the DICOM directory.

        Returns
        -------
        None.

        """
        
        if not subject_input_state_list.is_ref_loaded:
            return

        # Check for FreeSurfer requirement and request
        is_freesurfer = dependency_manager.is_freesurfer() and subject_config.get_workflow_freesurfer_pref()
        is_hippo_amyg_labels = dependency_manager.is_freesurfer_matlab() and subject_config.get_workflow_hippo_pref()

        # Check for FLAT1 requirement and request
        is_flat1 = subject_config.getboolean_safe(DIL.T13D, 'flat1') and subject_input_state_list[DIL.FLAIR3D].loaded
        # Check for Asymmetry Index request
        is_ai = ((subject_config.getboolean_safe(DIL.PET, 'ai') and subject_input_state_list[DIL.PET].loaded) or
                 (subject_config.getboolean_safe(DIL.ASL, 'ai') and subject_input_state_list[DIL.ASL].loaded))
        # Check for Tractography request
        is_tractography = subject_config.getboolean_safe(DIL.DTI, 'tractography')
        # CPU cores and memory management
        self.is_resource_monitor = global_config.getboolean_safe(GlobalPrefCategoryList.PERFORMANCE, 'resource_monitor')
        self.max_cpu = global_config.getint_safe(GlobalPrefCategoryList.PERFORMANCE, 'max_subj_cu')
        if self.max_cpu < 1:
            self.max_cpu = cpu_count()
        self.multicore_node_limit = global_config.getenum_safe(GlobalPrefCategoryList.PERFORMANCE, 'multicore_node_limit')
        # GPU management
        self.max_gpu = global_config.getint_safe(GlobalPrefCategoryList.PERFORMANCE, 'max_subj_gpu')
        if self.max_gpu < 0:
            self.max_gpu = MonitoredMultiProcPlugin.gpu_count()
        try:
            if not dependency_manager.is_cuda():
                subject_config[DIL.DTI]["cuda"] = "false"
            else:
                subject_config[DIL.DTI]["cuda"] = global_config[GlobalPrefCategoryList.PERFORMANCE]["cuda"]
        except:
            subject_config[DIL.DTI]["cuda"] = "false"

        subject_config.sections()

        max_node_cpu = max(int(self.max_cpu / 2), 1)

        # 3D T1w
        ref_dir = subject_input_state_list.get_dicom_dir(DIL.T13D)
        t1 = ref_workflow(DIL.T13D.value.workflow_name, ref_dir, subject_config[DIL.T13D])
        t1.long_name = "3D T1w analysis"
        self.add_nodes([t1])

        t1.sink_result(self.base_dir, "outputnode", 'ref', self.Result_DIR)
        t1.sink_result(self.base_dir, "outputnode", 'ref_brain', self.Result_DIR)

        if is_ai:
            # Non linear registration for Asymmetry Index
            sym = nonlinear_reg_workflow("sym")
            sym.long_name = "Symmetric atlas registration"

            sym_inputnode = sym.get_node("inputnode")
            sym_template = swane_supplement.sym_template
            sym_inputnode.inputs.atlas = sym_template
            self.connect(t1, "outputnode.ref_brain", sym, "inputnode.in_file")

        if is_freesurfer:
            # FreeSurfer analysis
            freesurfer = freesurfer_workflow("freesurfer", is_hippo_amyg_labels, max_cpu=self.max_cpu, multicore_node_limit=self.multicore_node_limit)
            freesurfer.long_name = "Freesurfer analysis"

            freesurfer_inputnode = freesurfer.get_node("inputnode")
            freesurfer_inputnode.inputs.subjects_dir = self.base_dir
            self.connect(t1, "outputnode.ref", freesurfer, "inputnode.ref")

            freesurfer.sink_result(self.base_dir, "outputnode", 'pial', self.Result_DIR)
            freesurfer.sink_result(self.base_dir, "outputnode", 'white', self.Result_DIR)
            freesurfer.sink_result(self.base_dir, "outputnode", 'vol_label_file', self.Result_DIR)
            if is_hippo_amyg_labels:
                regex_subs = [("-T1.*.mgz", ".mgz")]
                freesurfer.sink_result(self.base_dir, "outputnode", 'lh_hippoAmygLabels', 'scene.segmentHA', regex_subs)
                freesurfer.sink_result(self.base_dir, "outputnode", 'rh_hippoAmygLabels', 'scene.segmentHA', regex_subs)

        if subject_input_state_list[DIL.FLAIR3D].loaded:
            # 3D Flair analysis
            flair_dir = subject_input_state_list.get_dicom_dir(DIL.FLAIR3D)
            flair = linear_reg_workflow(DIL.FLAIR3D.value.workflow_name, flair_dir, subject_config[DIL.FLAIR3D])
            flair.long_name = "3D Flair analysis"
            self.add_nodes([flair])

            flair_inputnode = flair.get_node("inputnode")
            flair_inputnode.inputs.crop = True
            flair_inputnode.inputs.output_name = "r-flair_brain.nii.gz"
            self.connect(t1, "outputnode.ref_brain", flair, "inputnode.reference")

            flair.sink_result(self.base_dir, "outputnode", 'registered_file', self.Result_DIR)

            # if is_freesurfer:
            #     from swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow import freesurfer_asymmetry_index_workflow
            #     flair_ai = freesurfer_asymmetry_index_workflow(name="flair_ai")
            #     self.connect(flair, "outputnode.registered_file", flair_ai, "inputnode.in_file")
            #     self.connect(freesurfer, "outputnode.vol_label_file_nii", flair_ai, "inputnode.seg_file")

        if is_flat1:
            # Non linear registration to MNI1mm Atlas for FLAT1
            mni1 = nonlinear_reg_workflow("mni1")
            mni1.long_name = "MNI atlas registration"

            mni1_inputnode = mni1.get_node("inputnode")
            mni1_path = abspath(os.path.join(os.environ["FSLDIR"], 'data/standard/MNI152_T1_1mm_brain.nii.gz'))
            mni1_inputnode.inputs.atlas = mni1_path
            self.connect(t1, "outputnode.ref_brain", mni1, "inputnode.in_file")

            # FLAT1 analysis
            flat1 = flat1_workflow("FLAT1", mni1_path)
            flat1.long_name = "FLAT1 analysis"

            self.connect(t1, "outputnode.ref_brain", flat1, "inputnode.ref_brain")
            self.connect(flair, "outputnode.registered_file", flat1, "inputnode.flair_brain")
            self.connect(mni1, "outputnode.fieldcoeff_file", flat1, "inputnode.ref_2_mni1_warp")
            self.connect(mni1, "outputnode.inverse_warp", flat1, "inputnode.ref_2_mni1_inverse_warp")

            flat1.sink_result(self.base_dir, "outputnode", "extension_z", self.Result_DIR)
            flat1.sink_result(self.base_dir, "outputnode", "junction_z", self.Result_DIR)
            flat1.sink_result(self.base_dir, "outputnode", "binary_flair", self.Result_DIR)

        for plane in PLANES:
            if DIL['FLAIR2D_%s' % plane.name] in subject_input_state_list and subject_input_state_list[DIL['FLAIR2D_%s' % plane.name]].loaded:
                flair_dir = subject_input_state_list.get_dicom_dir(DIL['FLAIR2D_%s' % plane.name])
                flair2d = linear_reg_workflow(DIL['FLAIR2D_%s' % plane.name].value.workflow_name, flair_dir, None, is_volumetric=False)
                flair2d.long_name = "2D %s FLAIR analysis" % plane.value
                self.add_nodes([flair2d])

                flair2d_tra_inputnode = flair2d.get_node("inputnode")
                flair2d_tra_inputnode.inputs.crop = False
                flair2d_tra_inputnode.inputs.output_name = "r-flair2d_%s_brain.nii.gz" % plane
                self.connect(t1, "outputnode.ref_brain", flair2d, "inputnode.reference")

                flair2d.sink_result(self.base_dir, "outputnode", 'registered_file', self.Result_DIR)

        if subject_input_state_list[DIL.MDC].loaded:
            # MDC analysis
            mdc_dir = subject_input_state_list.get_dicom_dir(DIL.MDC)
            mdc = linear_reg_workflow(DIL.MDC.value.workflow_name, mdc_dir, subject_config[DIL.MDC])
            mdc.long_name = "Post-contrast 3D T1w analysis"
            self.add_nodes([mdc])

            mdc_inputnode = mdc.get_node("inputnode")
            mdc_inputnode.inputs.crop = True
            mdc_inputnode.inputs.output_name = "r-mdc_brain.nii.gz"
            self.connect(t1, "outputnode.ref_brain", mdc, "inputnode.reference")

            mdc.sink_result(self.base_dir, "outputnode", 'registered_file', self.Result_DIR)

        if subject_input_state_list[DIL.ASL].loaded:
            # ASL analysis
            asl_dir = subject_input_state_list.get_dicom_dir(DIL.ASL)
            asl = func_map_workflow(DIL.ASL.value.workflow_name, asl_dir, is_freesurfer, subject_config[DIL.ASL])
            asl.long_name = "Arterial Spin Labelling analysis"

            self.connect(t1, 'outputnode.ref_brain', asl, 'inputnode.reference')
            self.connect(t1, 'outputnode.ref_mask', asl, 'inputnode.brain_mask')

            asl.sink_result(self.base_dir, "outputnode", 'registered_file', self.Result_DIR)

            if is_freesurfer:
                self.connect(freesurfer, 'outputnode.subjects_dir', asl, 'inputnode.freesurfer_subjects_dir')
                self.connect(freesurfer, 'outputnode.subject_id', asl, 'inputnode.freesurfer_subject_id')
                self.connect(freesurfer, 'outputnode.bgROI', asl, 'inputnode.bgROI')

                asl.sink_result(self.base_dir, "outputnode", 'surf_lh', self.Result_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'surf_rh', self.Result_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'zscore', self.Result_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'zscore_surf_lh', self.Result_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'zscore_surf_rh', self.Result_DIR)

            if subject_config.getboolean_safe(DIL.ASL, 'ai'):
                self.connect(sym, 'outputnode.fieldcoeff_file', asl, 'inputnode.ref_2_sym_warp')
                self.connect(sym, 'outputnode.inverse_warp', asl, 'inputnode.ref_2_sym_invwarp')

                asl.sink_result(self.base_dir, "outputnode", 'ai', self.Result_DIR)

                if is_freesurfer:
                    asl.sink_result(self.base_dir, "outputnode", 'ai_surf_lh', self.Result_DIR)
                    asl.sink_result(self.base_dir, "outputnode", 'ai_surf_rh', self.Result_DIR)

        if subject_input_state_list[DIL.PET].loaded:  # and check_input['ct_brain']:
            # PET analysis
            pet_dir = subject_input_state_list.get_dicom_dir(DIL.PET)
            pet = func_map_workflow(DIL.PET.value.workflow_name, pet_dir, is_freesurfer, subject_config[DIL.PET])
            pet.long_name = "Pet analysis"

            self.connect(t1, 'outputnode.ref', pet, 'inputnode.reference')
            self.connect(t1, 'outputnode.ref_mask', pet, 'inputnode.brain_mask')

            pet.sink_result(self.base_dir, "outputnode", 'registered_file', self.Result_DIR)

            if is_freesurfer:
                self.connect(freesurfer, 'outputnode.subjects_dir', pet, 'inputnode.freesurfer_subjects_dir')
                self.connect(freesurfer, 'outputnode.subject_id', pet, 'inputnode.freesurfer_subject_id')
                self.connect(freesurfer, 'outputnode.bgROI', pet, 'inputnode.bgROI')

                pet.sink_result(self.base_dir, "outputnode", 'surf_lh', self.Result_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'surf_rh', self.Result_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore', self.Result_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore_surf_lh', self.Result_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore_surf_rh', self.Result_DIR)

                # TODO work in progress for segmentation based asymmetry study
                # from swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow import freesurfer_asymmetry_index_workflow
                # pet_ai = freesurfer_asymmetry_index_workflow(name="pet_ai")
                # self.connect(pet, "outputnode.registered_file", pet_ai, "inputnode.in_file")
                # self.connect(freesurfer, "outputnode.vol_label_file_nii", pet_ai, "inputnode.seg_file")

            if subject_config.getboolean_safe(DIL.PET, 'ai'):
                self.connect(sym, 'outputnode.fieldcoeff_file', pet, 'inputnode.ref_2_sym_warp')
                self.connect(sym, 'outputnode.inverse_warp', pet, 'inputnode.ref_2_sym_invwarp')

                pet.sink_result(self.base_dir, "outputnode", 'ai', self.Result_DIR)

                if is_freesurfer:
                    pet.sink_result(self.base_dir, "outputnode", 'ai_surf_lh', self.Result_DIR)
                    pet.sink_result(self.base_dir, "outputnode", 'ai_surf_rh', self.Result_DIR)

        if subject_input_state_list[DIL.VENOUS].loaded and subject_input_state_list[DIL.VENOUS].volumes + subject_input_state_list[DIL.VENOUS2].volumes == 2:
            # Venous analysis
            venous_dir = subject_input_state_list.get_dicom_dir(DIL.VENOUS)
            venous2_dir = None
            if subject_input_state_list[DIL.VENOUS2].loaded:
                venous2_dir = subject_input_state_list.get_dicom_dir(DIL.VENOUS2)
            venous = venous_workflow(DIL.VENOUS.value.workflow_name, venous_dir, subject_config[DIL.VENOUS], venous2_dir)
            venous.long_name = "Venous MRA analysis"

            self.connect(t1, "outputnode.ref_brain", venous, "inputnode.ref_brain")

            venous.sink_result(self.base_dir, "outputnode", 'veins', self.Result_DIR)

        if subject_input_state_list[DIL.DTI].loaded:
            # DTI analysis
            dti_dir = subject_input_state_list.get_dicom_dir(DIL.DTI)
            mni_dir = abspath(os.path.join(os.environ["FSLDIR"], 'data/standard/MNI152_T1_2mm_brain.nii.gz'))

            dti_preproc = dti_preproc_workflow(DIL.DTI.value.workflow_name, dti_dir, subject_config[DIL.DTI], mni_dir, max_cpu=self.max_cpu, multicore_node_limit=self.multicore_node_limit)
            dti_preproc.long_name = "Diffusion Tensor Imaging preprocessing"
            self.connect(t1, "outputnode.ref_brain", dti_preproc, "inputnode.ref_brain")

            dti_preproc.sink_result(self.base_dir, "outputnode", 'FA', self.Result_DIR)

            if is_tractography:
                for tract in TRACTS.keys():
                    try:
                        if not subject_config.getboolean_safe(DIL.DTI, tract):
                            continue
                    except:
                        continue
                    
                    tract_workflow = tractography_workflow(tract, subject_config[DIL.DTI])
                    if tract_workflow is not None:
                        tract_workflow.long_name = TRACTS[tract][0] + " tractography"
                        self.connect(dti_preproc, "outputnode.fsamples", tract_workflow, "inputnode.fsamples")
                        self.connect(dti_preproc, "outputnode.nodiff_mask_file", tract_workflow, "inputnode.mask")
                        self.connect(dti_preproc, "outputnode.phsamples", tract_workflow, "inputnode.phsamples")
                        self.connect(dti_preproc, "outputnode.thsamples", tract_workflow, "inputnode.thsamples")
                        self.connect(t1, "outputnode.ref_brain", tract_workflow, "inputnode.ref_brain")
                        self.connect(dti_preproc, "outputnode.diff2ref_mat", tract_workflow, "inputnode.diff2ref_mat")
                        self.connect(dti_preproc, "outputnode.ref2diff_mat", tract_workflow, "inputnode.ref2diff_mat")
                        self.connect(dti_preproc, "outputnode.mni2ref_warp", tract_workflow, "inputnode.mni2ref_warp")

                        for side in SIDES:
                            tract_workflow.sink_result(self.base_dir, "outputnode", "waytotal_%s" % side,
                                                       self.Result_DIR + ".dti")
                            tract_workflow.sink_result(self.base_dir, "outputnode", "fdt_paths_%s" % side,
                                                       self.Result_DIR + ".dti")

        # Check for Task FMRI sequences
        for y in range(FMRI_NUM):

            if subject_input_state_list[DIL['FMRI_%d' % y]].loaded:

                dicom_dir = subject_input_state_list.get_dicom_dir(DIL['FMRI_%d' % y])
                fMRI = task_fMRI_workflow(DIL['FMRI_%d' % y].value.workflow_name, dicom_dir, subject_config[DIL['FMRI_%d' % y]], self.base_dir)
                fMRI.long_name = "Task fMRI analysis - %d" % y
                self.connect(t1, "outputnode.ref_brain", fMRI, "inputnode.ref_BET")
                fMRI.sink_result(self.base_dir, "outputnode", 'threshold_file_1', self.Result_DIR + '.fMRI')
                if subject_config.getenum_safe(DIL['FMRI_%d' % y], "block_design") == BLOCK_DESIGN.RARB:
                    fMRI.sink_result(self.base_dir, "outputnode", 'threshold_file_2', self.Result_DIR + '.fMRI')
