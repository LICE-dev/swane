import os
from multiprocessing import cpu_count
from os.path import abspath

import swane_supplement

from swane.utils.ConfigManager import ConfigManager
from swane.utils.DataInput import DataInputList
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
from swane.utils.preference_list import TRACTS
from swane.utils.DependencyManager import DependencyManager
from swane.utils.preference_list import MAIN, PERFORMANCE

DEBUG = False


# TODO implementazione error manager
class MainWorkflow(CustomWorkflow):
    SCENE_DIR = 'scene'

    def add_input_folders(self, global_config: ConfigManager, pt_config: ConfigManager, dependency_manager: DependencyManager, data_input_list: DataInputList):
        """
        Create the Workflows and their sub-workflows based on the list of available data inputs 

        Parameters
        ----------
        global_config : ConfigManager
            The app global configurations.
        pt_config : ConfigManager
            The patient specific configurations.
        data_input_list : DataInputList
            The list of all available input data from the DICOM directory.

        Returns
        -------
        None.

        """
        
        if not data_input_list.is_ref_loaded:
            return

        # Check for FreeSurfer requirement and request
        is_freesurfer = dependency_manager.is_freesurfer() and pt_config.get_pt_wf_freesurfer()
        is_hippo_amyg_labels = dependency_manager.is_freesurfer_matlab() and pt_config.get_wf_hippo_pref()

        # Check for FLAT1 requirement and request
        try:
            is_flat1 = pt_config.getboolean(DataInputList.T13D, 'flat1') and data_input_list[DataInputList.FLAIR3D].loaded
        except:
            is_flat1 = False
        # Check for Asymmetry Index request
        try:
            is_ai = pt_config.getboolean(DataInputList.PET, 'ai') or pt_config.getboolean(DataInputList.ASL, 'ai')
        except:
            is_ai = False
        # Check for Tractography request
        try:
            is_tractography = pt_config.getboolean(DataInputList.DTI, 'tractography')
        except:
            is_tractography = False

        # CPU cores and memory management
        try:
            self.is_resource_monitor = global_config.getboolean(PERFORMANCE, 'resourceMonitor')
        except:
            self.is_resource_monitor = False
        try:
            self.max_cpu = global_config.getint(PERFORMANCE, 'max_pt_cpu')
        except:
            self.max_cpu = -1

        if self.max_cpu < 1:
            self.max_cpu = cpu_count()

        try:
            self.multicore_node_limit = global_config.getint(PERFORMANCE, 'multicore_node_limit')
        except:
            self.multicore_node_limit = 0
        try:
            self.max_gpu = global_config.getint(MAIN, 'max_pt_gpu')
            if self.max_gpu < 0:
                self.max_gpu = 1
        except:
            self.max_gpu = 1
        try:
            if not dependency_manager.is_cuda():
                pt_config[DataInputList.DTI]["cuda"] = "false"
            else:
                pt_config[DataInputList.DTI]["cuda"] = global_config[PERFORMANCE]["cuda"]
        except:
            pt_config[DataInputList.DTI]["cuda"] = "false"

        max_node_cpu = max(int(self.max_cpu / 2), 1)

        # 3D T1w
        ref_dir = data_input_list.get_dicom_dir(DataInputList.T13D)
        t1 = ref_workflow(data_input_list[DataInputList.T13D].wf_name, ref_dir, pt_config[DataInputList.T13D])
        t1.long_name = "3D T1w analysis"
        self.add_nodes([t1])

        t1.sink_result(self.base_dir, "outputnode", 'ref', self.SCENE_DIR)
        t1.sink_result(self.base_dir, "outputnode", 'ref_brain', self.SCENE_DIR)

        if is_ai and (data_input_list[DataInputList.ASL].loaded or data_input_list[DataInputList.PET].loaded):
            # Non linear registration for Asymmetry Index
            sym = nonlinear_reg_workflow("sym")
            sym.long_name = "Symmetric atlas registration"

            sym_inputnode = sym.get_node("inputnode")
            sym_template = swane_supplement.sym_template
            sym_inputnode.inputs.atlas = sym_template
            self.connect(t1, "outputnode.ref_brain", sym, "inputnode.in_file")

        if is_freesurfer:
            # FreeSurfer analysis
            freesurfer = freesurfer_workflow("freesurfer", is_hippo_amyg_labels)
            freesurfer.long_name = "Freesurfer analysis"

            # TODO: check freesurfer cpu usage and parallelization
            freesurfer_inputnode = freesurfer.get_node("inputnode")
            freesurfer_inputnode.inputs.max_node_cpu = max_node_cpu
            freesurfer_inputnode.inputs.subjects_dir = self.base_dir
            self.connect(t1, "outputnode.ref", freesurfer, "inputnode.ref")

            freesurfer.sink_result(self.base_dir, "outputnode", 'pial', self.SCENE_DIR)
            freesurfer.sink_result(self.base_dir, "outputnode", 'white', self.SCENE_DIR)
            freesurfer.sink_result(self.base_dir, "outputnode", 'vol_label_file', self.SCENE_DIR)
            if is_hippo_amyg_labels:
                regex_subs = [("-T1.*.mgz", ".mgz")]
                freesurfer.sink_result(self.base_dir, "outputnode", 'lh_hippoAmygLabels', 'scene.segmentHA', regex_subs)
                freesurfer.sink_result(self.base_dir, "outputnode", 'rh_hippoAmygLabels', 'scene.segmentHA', regex_subs)

        if data_input_list[DataInputList.FLAIR3D].loaded:
            # 3D Flair analysis
            flair_dir = data_input_list.get_dicom_dir(DataInputList.FLAIR3D)
            flair = linear_reg_workflow(data_input_list[DataInputList.FLAIR3D].wf_name, flair_dir, pt_config[DataInputList.FLAIR3D])
            flair.long_name = "3D Flair analysis"
            self.add_nodes([flair])

            flair_inputnode = flair.get_node("inputnode")
            flair_inputnode.inputs.frac = 0.5
            flair_inputnode.inputs.crop = True
            flair_inputnode.inputs.output_name = "r-flair_brain.nii.gz"
            self.connect(t1, "outputnode.ref_brain", flair, "inputnode.reference")

            flair.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

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

            flat1.sink_result(self.base_dir, "outputnode", "extension_z", self.SCENE_DIR)
            flat1.sink_result(self.base_dir, "outputnode", "junction_z", self.SCENE_DIR)
            flat1.sink_result(self.base_dir, "outputnode", "binary_flair", self.SCENE_DIR)

        for plane in DataInputList.PLANES:
            if DataInputList.FLAIR2D+'_%s' % plane in data_input_list and data_input_list[DataInputList.FLAIR2D+'_%s' % plane].loaded:
                flair_dir = data_input_list.get_dicom_dir(DataInputList.FLAIR2D+'_%s' % plane)
                flair2d = linear_reg_workflow(data_input_list[DataInputList.FLAIR2D+'_%s' % plane].wf_name, flair_dir, None, is_volumetric=False)
                flair2d.long_name = "2D %s FLAIR analysis" % plane
                self.add_nodes([flair2d])

                flair2d_tra_inputnode = flair2d.get_node("inputnode")
                flair2d_tra_inputnode.inputs.frac = 0.5
                flair2d_tra_inputnode.inputs.crop = False
                flair2d_tra_inputnode.inputs.output_name = "r-flair2d_%s_brain.nii.gz" % plane
                self.connect(t1, "outputnode.ref_brain", flair2d, "inputnode.reference")

                flair2d.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

        if data_input_list[DataInputList.MDC].loaded:
            # MDC analysis
            mdc_dir = data_input_list.get_dicom_dir(DataInputList.MDC)
            mdc = linear_reg_workflow(data_input_list[DataInputList.MDC].wf_name, mdc_dir, pt_config[DataInputList.MDC])
            mdc.long_name = "Post-contrast 3D T1w analysis"
            self.add_nodes([mdc])

            mdc_inputnode = mdc.get_node("inputnode")
            mdc_inputnode.inputs.frac = 0.3
            mdc_inputnode.inputs.crop = True
            mdc_inputnode.inputs.output_name = "r-mdc_brain.nii.gz"
            self.connect(t1, "outputnode.ref_brain", mdc, "inputnode.reference")

            mdc.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

        if data_input_list[DataInputList.ASL].loaded:
            # ASL analysis
            asl_dir = data_input_list.get_dicom_dir(DataInputList.ASL)
            asl = func_map_workflow(data_input_list[DataInputList.ASL].wf_name, asl_dir, is_freesurfer, pt_config[DataInputList.ASL])
            asl.long_name = "Arterial Spin Labelling analysis"

            self.connect(t1, 'outputnode.ref_brain', asl, 'inputnode.reference')
            self.connect(t1, 'outputnode.ref_mask', asl, 'inputnode.brain_mask')

            asl.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

            if is_freesurfer:
                self.connect(freesurfer, 'outputnode.subjects_dir', asl, 'inputnode.freesurfer_subjects_dir')
                self.connect(freesurfer, 'outputnode.subject_id', asl, 'inputnode.freesurfer_subject_id')
                self.connect(freesurfer, 'outputnode.bgROI', asl, 'inputnode.bgROI')

                asl.sink_result(self.base_dir, "outputnode", 'surf_lh', self.SCENE_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'surf_rh', self.SCENE_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'zscore', self.SCENE_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'zscore_surf_lh', self.SCENE_DIR)
                asl.sink_result(self.base_dir, "outputnode", 'zscore_surf_rh', self.SCENE_DIR)

            if is_ai:
                self.connect(sym, 'outputnode.fieldcoeff_file', asl, 'inputnode.ref_2_sym_warp')
                self.connect(sym, 'outputnode.inverse_warp', asl, 'inputnode.ref_2_sym_invwarp')

                asl.sink_result(self.base_dir, "outputnode", 'ai', self.SCENE_DIR)

                if is_freesurfer:
                    asl.sink_result(self.base_dir, "outputnode", 'ai_surf_lh', self.SCENE_DIR)
                    asl.sink_result(self.base_dir, "outputnode", 'ai_surf_rh', self.SCENE_DIR)

        if data_input_list[DataInputList.PET].loaded:  # and check_input['ct_brain']:
            # PET analysis
            pet_dir = data_input_list.get_dicom_dir(DataInputList.PET)
            pet = func_map_workflow(data_input_list[DataInputList.PET].wf_name, pet_dir, is_freesurfer, pt_config[DataInputList.PET])
            pet.long_name = "Pet analysis"

            self.connect(t1, 'outputnode.ref', pet, 'inputnode.reference')
            self.connect(t1, 'outputnode.ref_mask', pet, 'inputnode.brain_mask')

            pet.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

            if is_freesurfer:
                self.connect(freesurfer, 'outputnode.subjects_dir', pet, 'inputnode.freesurfer_subjects_dir')
                self.connect(freesurfer, 'outputnode.subject_id', pet, 'inputnode.freesurfer_subject_id')
                self.connect(freesurfer, 'outputnode.bgROI', pet, 'inputnode.bgROI')

                pet.sink_result(self.base_dir, "outputnode", 'surf_lh', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'surf_rh', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore_surf_lh', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore_surf_rh', self.SCENE_DIR)

                # TODO work in progress for segmentation based asymmetry study
                # from swane.nipype_pipeline.workflows.freesurfer_asymmetry_index_workflow import freesurfer_asymmetry_index_workflow
                # pet_ai = freesurfer_asymmetry_index_workflow(name="pet_ai")
                # self.connect(pet, "outputnode.registered_file", pet_ai, "inputnode.in_file")
                # self.connect(freesurfer, "outputnode.vol_label_file_nii", pet_ai, "inputnode.seg_file")

            if is_ai:
                self.connect(sym, 'outputnode.fieldcoeff_file', pet, 'inputnode.ref_2_sym_warp')
                self.connect(sym, 'outputnode.inverse_warp', pet, 'inputnode.ref_2_sym_invwarp')

                pet.sink_result(self.base_dir, "outputnode", 'ai', self.SCENE_DIR)

                if is_freesurfer:
                    pet.sink_result(self.base_dir, "outputnode", 'ai_surf_lh', self.SCENE_DIR)
                    pet.sink_result(self.base_dir, "outputnode", 'ai_surf_rh', self.SCENE_DIR)

        if data_input_list[DataInputList.VENOUS].loaded and data_input_list[DataInputList.VENOUS].volumes + data_input_list[DataInputList.VENOUS2].volumes == 2:
            # Venous analysis
            venous_dir = data_input_list.get_dicom_dir(DataInputList.VENOUS)
            venous2_dir = None
            if data_input_list[DataInputList.VENOUS2].loaded:
                venous2_dir = data_input_list.get_dicom_dir(DataInputList.VENOUS2)
            venous = venous_workflow(data_input_list[DataInputList.VENOUS].wf_name, venous_dir, pt_config[DataInputList.VENOUS], venous2_dir)
            venous.long_name = "Venous MRA analysis"

            self.connect(t1, "outputnode.ref_brain", venous, "inputnode.ref_brain")

            venous.sink_result(self.base_dir, "outputnode", 'veins', self.SCENE_DIR)

        if data_input_list[DataInputList.DTI].loaded:
            # DTI analysis
            dti_dir = data_input_list.get_dicom_dir(DataInputList.DTI)
            mni_dir = abspath(os.path.join(os.environ["FSLDIR"], 'data/standard/MNI152_T1_2mm_brain.nii.gz'))

            dti_preproc = dti_preproc_workflow(data_input_list[DataInputList.DTI].wf_name, dti_dir, pt_config[DataInputList.DTI], mni_dir, max_cpu=self.max_cpu, multicore_node_limit=self.multicore_node_limit)
            dti_preproc.long_name = "Diffusion Tensor Imaging preprocessing"
            self.connect(t1, "outputnode.ref_brain", dti_preproc, "inputnode.ref_brain")

            dti_preproc.sink_result(self.base_dir, "outputnode", 'FA', self.SCENE_DIR)

            if is_tractography:
                for tract in TRACTS.keys():
                    try:
                        if not pt_config.getboolean(DataInputList.DTI, tract):
                            continue
                    except:
                        continue
                    
                    tract_workflow = tractography_workflow(tract, pt_config[DataInputList.DTI])
                    tract_workflow.long_name = TRACTS[tract][0] + " tractography"
                    if tract_workflow is not None:
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
                                                             self.SCENE_DIR + ".dti")
                            tract_workflow.sink_result(self.base_dir, "outputnode", "fdt_paths_%s" % side,
                                                             self.SCENE_DIR + ".dti")

        # Check for Task FMRI sequences
        for y in range(DataInputList.FMRI_NUM):

            if data_input_list[DataInputList.FMRI+'_%d' % y].loaded:

                try:
                    task_a_name = pt_config[DataInputList.FMRI+'_%d' % y]["task_a_name"]
                except:
                    task_a_name = "Task A"

                try:
                    task_b_name = pt_config[DataInputList.FMRI+'_%d' % y]["task_b_name"]
                except:
                    task_b_name = "Task B"

                try:
                    task_duration = pt_config[DataInputList.FMRI+'_%d' % y].getint('task_duration')
                except:
                    task_duration = 30

                try:
                    rest_duration = pt_config[DataInputList.FMRI+'_%d' % y].getint('rest_duration')
                except:
                    rest_duration = 30

                try:
                    TR = pt_config[DataInputList.FMRI+'_%d' % y].getfloat('tr')
                except:
                    TR = -1

                try:
                    slice_timing = pt_config[DataInputList.FMRI+'_%d' % y].getint('slice_timing')
                except:
                    slice_timing = 0

                try:
                    n_vols = pt_config[DataInputList.FMRI+'_%d' % y].getint('n_vols')
                except:
                    n_vols = -1

                try:
                    del_start_vols = pt_config[DataInputList.FMRI+'_%d' % y].getint('del_start_vols')
                except:
                    del_start_vols = 0

                try:
                    del_end_vols = pt_config[DataInputList.FMRI+'_%d' % y].getint('del_end_vols')
                except:
                    del_end_vols = 0

                try:
                    design_block = pt_config[DataInputList.FMRI+'_%d' % y].getint('block_design')
                except:
                    design_block = 0

                dicom_dir = data_input_list.get_dicom_dir(DataInputList.FMRI+'_%d' % y)
                fMRI = task_fMRI_workflow(data_input_list[DataInputList.FMRI+'_%d' % y].wf_name, dicom_dir, design_block, self.base_dir)
                fMRI.long_name = "Task fMRI analysis - %d" % y
                inputnode = fMRI.get_node("inputnode")
                inputnode.inputs.TR = TR
                inputnode.inputs.slice_timing = slice_timing
                inputnode.inputs.nvols = n_vols
                inputnode.inputs.task_a_name = task_a_name
                inputnode.inputs.task_b_name = task_b_name
                inputnode.inputs.task_duration = task_duration
                inputnode.inputs.rest_duration = rest_duration
                inputnode.inputs.del_start_vols = del_start_vols
                inputnode.inputs.del_end_vols = del_end_vols

                self.connect(t1, "outputnode.ref_brain", fMRI, "inputnode.ref_BET")
                fMRI.sink_result(self.base_dir, "outputnode", 'threshold_file_1', self.SCENE_DIR + '.fMRI')
                if design_block == 1:
                    fMRI.sink_result(self.base_dir, "outputnode", 'threshold_file_2', self.SCENE_DIR + '.fMRI')
