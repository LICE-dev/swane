import os
from multiprocessing import cpu_count
from os.path import abspath

import swane_supplement

from swane.nipype_pipeline.engine.CustomWorkflow import CustomWorkflow

from swane.nipype_pipeline.workflows.linear_reg_workflow import linear_reg_workflow
from swane.nipype_pipeline.workflows.task_fMRI_workflow import task_fMRI_workflow
from swane.nipype_pipeline.workflows.nonlinear_reg_workflow import nonlinear_reg_workflow
from swane.nipype_pipeline.workflows.ref_workflow import ref_workflow
from swane.nipype_pipeline.workflows.freesurfer_workflow import freesurfer_workflow
from swane.nipype_pipeline.workflows.domap_workflow import domap_workflow
from swane.nipype_pipeline.workflows.func_map_workflow import func_map_workflow
from swane.nipype_pipeline.workflows.venous_workflow import venous_workflow
from swane.nipype_pipeline.workflows.dti_preproc_workflow import dti_preproc_workflow
from swane.nipype_pipeline.workflows.tractography_workflow import tractography_workflow, SIDES
from swane.utils.DataInput import DataInputList


DEBUG = False


# TODO implementazione error manager
# todo valutare nome parlante per node
class MainWorkflow(CustomWorkflow):
    SCENE_DIR = 'scene'

    # TODO forse non serve, valutare eliminazione
    def __init__(self, name, base_dir=None):
        super(MainWorkflow, self).__init__(name, base_dir)

    def add_input_folders(self, global_config, pt_config, data_input_list):

        # global_config: configurazione globale dell'app
        # pt_config: configurazione specifica del paziente
        # data_input_list dictionary che ha come key tutte le possibili serie caricabili ciascuna con valore true/false

        if not data_input_list.is_ref_loaded:
            return

        # definizione dei boleani che saranno checkati prima della definizione dei specifici workflow
        is_freesurfer = pt_config.is_freesurfer() and pt_config.get_pt_wf_freesurfer()
        is_hippo_amyg_labels = pt_config.is_freesurfer_matlab() and pt_config.get_pt_wf_hippo()
        is_domap = pt_config.getboolean('WF_OPTION', 'DOmap') and data_input_list[DataInputList.FLAIR3D].loaded
        is_ai = pt_config.getboolean('WF_OPTION', 'ai')
        is_tractography = pt_config.getboolean('WF_OPTION', 'tractography')

        # definizione dei core assegnati al workflow e a ciascun nodo del workflow
        self.max_cpu = global_config.getint('MAIN', 'maxPtCPU')
        if self.max_cpu > 0:
            max_node_cpu = max(int(self.max_cpu / 2), 1)
        else:
            max_node_cpu = max(int((cpu_count() - 2) / 2), 1)

        # WORKFLOW 1: ELABORAZIONE T1 3D
        ref_dir = data_input_list.get_dicom_dir(DataInputList.T13D)
        t1 = ref_workflow(data_input_list[DataInputList.T13D].wf_name, ref_dir)
        t1.long_name = "3D T1w analysis"
        self.add_nodes([t1])

        t1.sink_result(self.base_dir, "outputnode", 'ref', self.SCENE_DIR)
        t1.sink_result(self.base_dir, "outputnode", 'ref_brain', self.SCENE_DIR)

        # WORKFLOW 3: REGISTRAZIONE AD ALTANTE SIMMETRICO PER EVENTUALI ASIMMETRY index
        if is_ai and (data_input_list[DataInputList.ASL].loaded or data_input_list[DataInputList.PET].loaded):
            sym = nonlinear_reg_workflow("sym")
            sym.long_name = "Symmetric atlas registration"

            sym_inputnode = sym.get_node("inputnode")
            sym_template = swane_supplement.sym_template
            sym_inputnode.inputs.atlas = sym_template
            self.connect(t1, "outputnode.ref_brain", sym, "inputnode.in_file")

        # WORKFLOW 4: ELABORAZIONE FREESURFER
        if is_freesurfer:

            freesurfer = freesurfer_workflow("freesurfer", is_hippo_amyg_labels)
            freesurfer.long_name = "Freesurfer analysis"

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

        # WORKFLOW 5: ELABORAZIONE FLAIR
        if data_input_list[DataInputList.FLAIR3D].loaded:
            flair_dir = data_input_list.get_dicom_dir(DataInputList.FLAIR3D)
            flair = linear_reg_workflow(data_input_list[DataInputList.FLAIR3D].wf_name, flair_dir)
            flair.long_name = "3D Flair analysis"
            self.add_nodes([flair])

            flair_inputnode = flair.get_node("inputnode")
            flair_inputnode.inputs.frac = 0.5
            flair_inputnode.inputs.crop = True
            flair_inputnode.inputs.output_name = "r-flair_brain.nii.gz"
            self.connect(t1, "outputnode.ref_brain", flair, "inputnode.reference")

            flair.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

        if is_domap:
            # WORKFLOW 6: REGISTRAZIONE AD ALTANTE MNI1mm (SERVE SOLO PER DOmap)
            mni1 = nonlinear_reg_workflow("mni1")
            mni1.long_name = "MNI atlas registration"

            mni1_inputnode = mni1.get_node("inputnode")
            mni1_path = abspath(os.path.join(os.environ["FSLDIR"], 'data/standard/MNI152_T1_1mm_brain.nii.gz'))
            mni1_inputnode.inputs.atlas = mni1_path
            self.connect(t1, "outputnode.ref_brain", mni1, "inputnode.in_file")

            # WORKFLOW 7: ELABORAZIONE script_DOmap
            domap = domap_workflow("DOmap", mni1_path)
            domap.long_name = "DOmap analysis"

            self.connect(t1, "outputnode.ref_brain", domap, "inputnode.ref_brain")
            self.connect(flair, "outputnode.registered_file", domap, "inputnode.flair_brain")
            self.connect(mni1, "outputnode.fieldcoeff_file", domap, "inputnode.ref_2_mni1_warp")
            self.connect(mni1, "outputnode.inverse_warp", domap, "inputnode.ref_2_mni1_inverse_warp")

            domap.sink_result(self.base_dir, "outputnode", "extension_z", self.SCENE_DIR)
            domap.sink_result(self.base_dir, "outputnode", "junction_z", self.SCENE_DIR)
            domap.sink_result(self.base_dir, "outputnode", "binary_flair", self.SCENE_DIR)

        for plane in DataInputList.PLANES:
            if DataInputList.FLAIR2D+'_%s' % plane in data_input_list and data_input_list[DataInputList.FLAIR2D+'_%s' % plane].loaded:
                flair_dir = data_input_list.get_dicom_dir(DataInputList.FLAIR2D+'_%s' % plane)
                flair2d = linear_reg_workflow(data_input_list[DataInputList.FLAIR2D+'_%s' % plane].wf_name, flair_dir, is_volumetric=False)
                flair2d.long_name = "2D %s FLAIR analysis" % plane
                self.add_nodes([flair2d])

                flair2d_tra_inputnode = flair2d.get_node("inputnode")
                flair2d_tra_inputnode.inputs.frac = 0.5
                flair2d_tra_inputnode.inputs.crop = False
                flair2d_tra_inputnode.inputs.output_name = "r-flair2d_%s_brain.nii.gz" % plane
                self.connect(t1, "outputnode.ref_brain", flair2d, "inputnode.reference")

                flair2d.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

        # WORKFLOW 11: ELABORAZIONE MDC
        if data_input_list[DataInputList.MDC].loaded:
            mdc_dir = data_input_list.get_dicom_dir(DataInputList.MDC)
            mdc = linear_reg_workflow(data_input_list[DataInputList.MDC].wf_name, mdc_dir)
            mdc.long_name = "Post-contrast 3D T1w analysis"
            self.add_nodes([mdc])

            mdc_inputnode = mdc.get_node("inputnode")
            mdc_inputnode.inputs.frac = 0.3
            mdc_inputnode.inputs.crop = True
            mdc_inputnode.inputs.output_name = "r-mdc_brain.nii.gz"
            self.connect(t1, "outputnode.ref_brain", mdc, "inputnode.reference")

            mdc.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

        # ELABORAZIONE ASL
        if data_input_list[DataInputList.ASL].loaded:

            asl_dir = data_input_list.get_dicom_dir(DataInputList.ASL)
            asl = func_map_workflow(data_input_list[DataInputList.ASL].wf_name, asl_dir, is_freesurfer, is_ai)
            asl.long_name = "Arterial Spin Labelling analysis"

            self.connect(t1, 'outputnode.ref_brain', asl, 'inputnode.reference')
            self.connect(t1, 'outputnode.ref_mask', asl, 'inputnode.brain_mask')

            asl.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

            if is_freesurfer:
                self.connect(freesurfer, 'outputnode.subjects_dir', asl, 'inputnode.freesurfer_subjects_dir')
                self.connect(freesurfer, 'outputnode.subject_id', asl, 'inputnode.freesurfer_subject_id')
                self.connect(freesurfer, 'outputnode.bgtROI', asl, 'inputnode.bgtROI')

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

        # ELABORAZIONE PET
        if data_input_list[DataInputList.PET].loaded:  # and check_input['ct_brain']:

            pet_dir = data_input_list.get_dicom_dir(DataInputList.PET)
            pet = func_map_workflow(data_input_list[DataInputList.PET].wf_name, pet_dir, is_freesurfer, is_ai)
            pet.long_name = "Pet analysis"

            self.connect(t1, 'outputnode.ref', pet, 'inputnode.reference')
            self.connect(t1, 'outputnode.ref_mask', pet, 'inputnode.brain_mask')

            pet.sink_result(self.base_dir, "outputnode", 'registered_file', self.SCENE_DIR)

            if is_freesurfer:
                self.connect(freesurfer, 'outputnode.subjects_dir', pet, 'inputnode.freesurfer_subjects_dir')
                self.connect(freesurfer, 'outputnode.subject_id', pet, 'inputnode.freesurfer_subject_id')
                self.connect(freesurfer, 'outputnode.bgtROI', pet, 'inputnode.bgtROI')

                pet.sink_result(self.base_dir, "outputnode", 'surf_lh', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'surf_rh', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore_surf_lh', self.SCENE_DIR)
                pet.sink_result(self.base_dir, "outputnode", 'zscore_surf_rh', self.SCENE_DIR)

            if is_ai:
                self.connect(sym, 'outputnode.fieldcoeff_file', pet, 'inputnode.ref_2_sym_warp')
                self.connect(sym, 'outputnode.inverse_warp', pet, 'inputnode.ref_2_sym_invwarp')

                pet.sink_result(self.base_dir, "outputnode", 'ai', self.SCENE_DIR)

                if is_freesurfer:
                    pet.sink_result(self.base_dir, "outputnode", 'ai_surf_lh', self.SCENE_DIR)
                    pet.sink_result(self.base_dir, "outputnode", 'ai_surf_rh', self.SCENE_DIR)

        # ELABORAZIONE VENOSA
        if data_input_list[DataInputList.VENOUS].loaded:
            venous_dir = data_input_list.get_dicom_dir(DataInputList.VENOUS)
            venous2_dir = None
            if data_input_list[DataInputList.VENOUS2].loaded:
                venous2_dir = data_input_list.get_dicom_dir(DataInputList.VENOUS2)
            venous = venous_workflow(data_input_list[DataInputList.VENOUS].wf_name, venous_dir, venous2_dir)
            venous.long_name = "Venous MRA analysis"

            self.connect(t1, "outputnode.ref_brain", venous, "inputnode.ref_brain")

            venous.sink_result(self.base_dir, "outputnode", 'veins', self.SCENE_DIR)

        # ELABORAZIONE DTI
        if data_input_list[DataInputList.DTI].loaded:

            dti_dir = data_input_list.get_dicom_dir(DataInputList.DTI)
            mni_dir = abspath(os.path.join(os.environ["FSLDIR"], 'data/standard/MNI152_T1_2mm_brain.nii.gz'))

            dti_preproc = dti_preproc_workflow(data_input_list[DataInputList.DTI].wf_name, dti_dir, mni_dir, is_tractography=is_tractography)
            dti_preproc.long_name = "Diffusion Tensor Imaging preprocessing"
            self.connect(t1, "outputnode.ref_brain", dti_preproc, "inputnode.ref_brain")

            dti_preproc.sink_result(self.base_dir, "outputnode", 'FA', self.SCENE_DIR)

            if is_tractography:
                for tract in pt_config['DEFAULTTRACTS'].keys():
                    if not pt_config.getboolean('DEFAULTTRACTS', tract):
                        continue
                    
                    tract_workflow = tractography_workflow(tract, 5)
                    tract_workflow.long_name = pt_config.TRACTS[tract][0] + " tractography"
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

        # CONTROLLO SE SONO STATE CARICATE SEQUENZE FMRI ED EVENTUALMENTE LE ANALIZZO SINGOLARMENTE
        for y in range(DataInputList.FMRI_NUM):

            if data_input_list[DataInputList.FMRI+'_%d' % y].loaded:

                task_a_name = pt_config['FMRI']["task_%d_name_a" % y]
                task_b_name = pt_config['FMRI']["task_%d_name_b" % y]
                task_duration = pt_config['FMRI'].getint('task_%d_duration' % y)
                rest_duration = pt_config['FMRI'].getint('rest_%d_duration' % y)

                try:
                    TR = pt_config['FMRI'].getfloat('task_%d_tr' % y)
                except:
                    TR = -1

                try:
                    slice_timing = pt_config['FMRI'].getint('task_%d_st' % y)
                except:
                    slice_timing = 0

                try:
                    nvols = pt_config['FMRI'].getint('task_%d_vols' % y)
                except:
                    nvols = -1

                try:
                    del_start_vols = pt_config['FMRI'].getint('task_%d_del_start_vols' % y)
                except:
                    del_start_vols = 0

                try:
                    del_end_vols = pt_config['FMRI'].getint('task_%d_del_end_vols' % y)
                except:
                    del_end_vols = 0

                try:
                    design_block = pt_config['FMRI'].getint('task_%d_blockdesign' % y)
                except:
                    design_block = 0

                dicom_dir = data_input_list.get_dicom_dir(DataInputList.FMRI+'_%d' % y)
                fMRI = task_fMRI_workflow(data_input_list[DataInputList.FMRI+'_%d' % y].wf_name, dicom_dir, design_block, self.base_dir)
                fMRI.long_name = "Task fMRI analysis - %d" % y
                inputnode = fMRI.get_node("inputnode")
                inputnode.inputs.TR = TR
                inputnode.inputs.slice_timing = slice_timing
                inputnode.inputs.nvols = nvols
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
