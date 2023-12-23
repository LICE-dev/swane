import os
import shutil
import pytest
from swane.config.ConfigManager import ConfigManager
from swane.config.config_enums import BLOCK_DESIGN, VEIN_DETECTION_MODE
from swane.utils.DependencyManager import DependencyManager
from swane.utils.Subject import Subject, SubjectRet
from swane.tests import TEST_DIR
from swane.workers.DicomSearchWorker import DicomSearchWorker
from swane.utils.DataInputList import DataInputList
from unittest.mock import ANY
from swane.config.preference_list import WF_PREFERENCES
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowReport, WorkflowSignals


@pytest.fixture(autouse=True)
def change_test_dir(request):
    test_dir = os.path.join(TEST_DIR, "workflow")
    test_main_working_directory = TestWorkflow.TEST_MAIN_WORKING_DIRECTORY
    shutil.rmtree(test_dir, ignore_errors=True)
    os.makedirs(test_dir, exist_ok=True)
    os.makedirs(test_main_working_directory, exist_ok=True)
    os.chdir(test_dir)


@pytest.fixture()
def test_patient():
    global_config = ConfigManager(global_base_folder=os.getcwd())
    global_config.set_main_working_directory(TestWorkflow.TEST_MAIN_WORKING_DIRECTORY)
    test_patient = Subject(global_config, DependencyManager())
    test_patient.create_new_subject_dir(TestWorkflow.TEST_PATIENT_NAME)
    return test_patient


def clear_data_and_check(patient: Subject, data_input: DataInputList, qtbot):
    patient.clear_import_folder(data_input)
    with qtbot.waitCallback() as call_back:
        patient.check_input_folder(data_input=data_input, status_callback=call_back)
    call_back.assert_called_with(ANY, SubjectRet.DataInputWarningNoDicom, ANY)


def import_from_path(patient: Subject, data_input: DataInputList, dicom_path: str, qtbot):
    patient.clear_import_folder(data_input)
    patient.reset_workflow()
    worker = DicomSearchWorker(dicom_path)
    worker.run()
    patient_list = worker.get_subject_list()
    exam_list = worker.get_exam_list(patient_list[0])
    series_list = worker.get_series_list(patient_list[0], exam_list[0])
    image_list, patient_name, mod, series_description, vols = worker.get_series_info(patient_list[0], exam_list[0],
                                                                                     series_list[0])
    import_ret = patient.dicom_import_to_folder(data_input=data_input, copy_list=image_list, vols=vols,
                                                     mod=mod, force_modality=True)
    assert import_ret == SubjectRet.DataImportCompleted
    with qtbot.waitCallback() as call_back:
        patient.check_input_folder(data_input=data_input, status_callback=call_back)
    call_back.assert_called_with(ANY, SubjectRet.DataInputValid, ANY)


class TestWorkflow:
    TEST_MAIN_WORKING_DIRECTORY = os.path.join(TEST_DIR, "workflow", "subjects")
    TEST_PATIENT_NAME = "pt_01"
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "dicom")

    TESTS = {
        # 'test_name': {
        #     'data': {
        #       DataInputList.T13D: "folder_name"
        #     },
        #     'preferences': {
        #         DataInputList.T13D: [
        #             ["preference_category", 'preference_value'],
        #         ]
        #     },
        #     'check_nodes': {
        #         "workflow_name": ["node_name", "input_name", "input_value"],
        #     },
        # },
        'base': {
            'preferences': {
                DataInputList.T13D: [
                    ["freesurfer", 'false'],
                    ["flat1", 'true'],  # no flat1 without flair, even if preference on
                ]
            },
            'check_nodes': {
                DataInputList.T13D.value.workflow_name: [
                    ["t13d_BET", "robust", True],
                    ["t13d_BET", "frac", WF_PREFERENCES[DataInputList.T13D]['bet_thr'].default]
                ],
                "-freesurfer": [],
                "-FLAT1": []    # no flat1 without flair, even if preference on
            },
            'execute': True
        },
        'ref_bias': {
            'preferences': {
                DataInputList.T13D: [
                    ["freesurfer", 'false'],
                    ["bet_bias_correction", "true"],
                    ['bet_thr', "0"],
                ]
            },
            'check_nodes': {
                DataInputList.T13D.value.workflow_name: [
                    ["t13d_BET", "reduce_bias", True],
                    ["t13d_BET", "frac", 0]
                ],
            },
        },
        'ref_invalid_thr': {
            'preferences': {
                DataInputList.T13D: [
                    ['bet_thr', "invalid"],
                ]
            },
            'check_nodes': {
                DataInputList.T13D.value.workflow_name: [
                    ["t13d_BET", "frac", WF_PREFERENCES[DataInputList.T13D]['bet_thr'].default]
                ],
            },
        },
        'freesurfer': {
            'preferences': {
                DataInputList.T13D: [
                    ["freesurfer", 'true'],
                    ["hippo_amyg_labels", "false"]
                ]
            },
            'check_nodes': {
                "freesurfer": ["-segmentHA"],
            },
        },
        'hippocampal': {
            'preferences': {
                DataInputList.T13D: [
                    ["freesurfer", 'true'],
                    ["hippo_amyg_labels", "true"]

                ]
            },
            'check_nodes': {
                "freesurfer": ["segmentHA"],
            },
        },
        'flair_and_flat1': {
            'data': {
                DataInputList.FLAIR3D: "singlevol"
            },
            'preferences': {
                DataInputList.T13D: [
                    ["flat1", 'true'],
                ]
            },
            'check_nodes': {
                DataInputList.FLAIR3D.value.workflow_name: [
                    ["flair3d_BET", "robust", True],
                ],
                "FLAT1": []
            },
        },
        'flair_bias': {
            'data': {
                DataInputList.FLAIR3D: "singlevol"
            },
            'preferences': {
                DataInputList.T13D: [
                    ["flat1", 'false'],
                ],
                DataInputList.FLAIR3D: [
                    ["bet_bias_correction", "true"],
                    ['bet_thr', "0"],
                ]
            },
            'check_nodes': {
                DataInputList.FLAIR3D.value.workflow_name: [
                    ["flair3d_BET", "reduce_bias", True],
                    ["flair3d_BET", "frac", 0]
                ],
                "-FLAT1": []
            },
        },
        'asl_ai': {
            'data': {
                DataInputList.ASL: "singlevol"
            },
            'preferences': {
                DataInputList.T13D: [
                    ["freesurfer", 'true'],
                ],
                DataInputList.ASL: [
                    ["ai", "true"]
                ]
            },
            'check_nodes': {
                DataInputList.ASL.value.workflow_name: [
                    ["asl_surf_lh"],
                    ["asl_ai"]
                ],
            },
        },
        'asl_base': {
            'data': {
                DataInputList.ASL: "singlevol"
            },
            'preferences': {
                DataInputList.T13D: [
                    ["freesurfer", 'false'],
                ],
                DataInputList.ASL: [
                    ["ai", "false"]
                ]
            },
            'check_nodes': {
                DataInputList.ASL.value.workflow_name: [
                    ["-asl_surf_lh"],
                    ["-asl_ai"]
                ],
            },
        },

        'venous_phase1+2': {
            'data': {
                DataInputList.VENOUS: "twovol"
            },
            'preferences': {
            },
            'check_nodes': {
                DataInputList.VENOUS.value.workflow_name: [
                    ["veins_bet", "frac", WF_PREFERENCES[DataInputList.VENOUS]['bet_thr'].default],
                    ["veins_split"]
                ],
            },
        },
        'venous_phase1only': {
            'data': {
                DataInputList.VENOUS: "singlevol"
            },
            'preferences': {
            },
            'check_nodes': {
                "-%s" % DataInputList.VENOUS.value.workflow_name: [],
            },
        },
        'venous_invalid_phase_detection': {
            'data': {
                DataInputList.VENOUS: "twovol"
            },
            'preferences': {
                DataInputList.VENOUS: [
                    ['vein_detection_mode', 'invalid']
                ]
            },
            'check_nodes': {
                DataInputList.VENOUS.value.workflow_name: [
                    ['veins_check', 'detection_mode', VEIN_DETECTION_MODE.SD]
                ],
            },
        },
        'venous_phase1+phase2': {
            'data': {
                DataInputList.VENOUS: "singlevol",
                DataInputList.VENOUS2: "singlevol",
            },
            'preferences': {
                DataInputList.VENOUS: [
                    ['bet_thr', "0"],
                    ['vein_detection_mode', VEIN_DETECTION_MODE.FIRST.name]
                ]
            },
            'check_nodes': {
                DataInputList.VENOUS.value.workflow_name: [
                    ["veins_bet", "frac", 0],
                    ["veins2_conv"],
                    ['veins_check', 'detection_mode', VEIN_DETECTION_MODE.FIRST]
                ],
            },
        },
        'dti_base': {
            'data': {
                DataInputList.DTI: "multivol",
            },
            'preferences': {
                DataInputList.DTI: [
                    ["tractography", "false"],
                ]
            },
            'check_nodes': {
                DataInputList.DTI.value.workflow_name: [
                    ["dti_eddy_files"],
                    ["-dti_bedpostx"],
                ],
            },
        },
        'dti_oldeddy_tracto': {
            'data': {
                DataInputList.DTI: "multivol",
            },
            'preferences': {
                DataInputList.DTI: [
                    ["tractography", "true"],
                    ["old_eddy_correct", "true"],
                    ["cst", "true"],
                    ["track_procs", "10"]
                ]
            },
            'check_nodes': {
                DataInputList.DTI.value.workflow_name: [
                    ["-dti_eddy_files"],
                    ["dti_bedpostx"],
                ],
                "tract_cst": [
                    ["random_seed", "seeds_n", 10]
                ]
            },
        },
        'fmri_base': {
            'data': {
                DataInputList["FMRI_0"]: "multivol",
            },
            'preferences': {
                DataInputList["FMRI_0"]: [
                    ["block_design", BLOCK_DESIGN.RARA.name],
                ]
            },
            'check_nodes': {
                DataInputList["FMRI_0"].value.workflow_name: [
                    ["-fmri_0_cluster_2"],
                ],
            },
        },
        'fmri_AB': {
            'data': {
                DataInputList["FMRI_0"]: "multivol",
            },
            'preferences': {
                DataInputList["FMRI_0"]: [
                    ["block_design", BLOCK_DESIGN.RARB.name],
                    ["task_duration", "invalid"],
                    ["rest_duration", "invalid"],
                    ["tr", "invalid"],
                    ["n_vols", "invalid"],
                    ["del_start_vols", "invalid"],
                    ["del_end_vols", "invalid"],
                ]
            },
            'check_nodes': {
                DataInputList["FMRI_0"].value.workflow_name: [
                    ["fmri_0_genSpec", "task_duration", WF_PREFERENCES[DataInputList["FMRI_0"]]["task_duration"].default],
                    ["fmri_0_genSpec", "rest_duration", WF_PREFERENCES[DataInputList["FMRI_0"]]["rest_duration"].default],
                    ["fmri_0_nvols", "force_value", -1],
                    ["fmri_0_getTR", "force_value", -1],
                    ["fmri_0_del_vols", "del_start_vols", WF_PREFERENCES[DataInputList["FMRI_0"]]["del_start_vols"].default],
                    ["fmri_0_del_vols", "del_end_vols", WF_PREFERENCES[DataInputList["FMRI_0"]]["del_end_vols"].default],
                    ["fmri_0_cluster_2"],
                ],
            },
        },
    }

    def test_1_workflow_generation(self, test_patient, qtbot):
        # check wk dependency
        assert test_patient.dependency_manager.is_fsl() is True, "missing fsl"
        assert test_patient.dependency_manager.is_dcm2niix() is True, "missing dcm2niix"

        last_test = None

        for test_name in TestWorkflow.TESTS:
            this_test = TestWorkflow.TESTS[test_name]

            if 'data' not in this_test:
                this_test['data'] = {}

            if DataInputList.T13D not in this_test['data']:
                this_test['data'][DataInputList.T13D] = "singlevol"

            # Clear all data, if necessary
            if last_test is not None:
                for data_input in DataInputList:
                    if data_input not in this_test['data'] or (data_input in last_test['data'] and this_test['data'][data_input] != last_test['data'][data_input]):
                        clear_data_and_check(test_patient, data_input, qtbot)

            # Import all data
            for data_input in this_test['data']:
                if last_test is not None and data_input in last_test['data'] and this_test['data'][data_input] == last_test['data'][data_input]:
                    pass
                else:
                    import_from_path(test_patient, data_input, os.path.join(TestWorkflow.DATA_DIR, this_test['data'][data_input]), qtbot)

                assert test_patient.input_state_list[data_input].loaded is True, "%s not loaded for %s" % (data_input, test_name)

            if 'preferences' in this_test:
                # Set workflow preferences
                for pref_cat in this_test['preferences']:
                    for pref in this_test['preferences'][pref_cat]:
                        test_patient.config[pref_cat][pref[0]] = pref[1]

            # Generate workflow
            assert test_patient.input_state_list.is_ref_loaded() is True, "missing t13d for " + test_name
            test_patient.reset_workflow()
            assert test_patient.generate_workflow(
                generate_graphs=False) == SubjectRet.GenWfCompleted, "Error generating workflow for " + test_name

            # Check desired nodes
            if 'check_nodes' not in this_test:
                this_test['check_nodes'] = {}
            for workflow_name in this_test['check_nodes']:
                sub_wf_presence = True
                if workflow_name[0] == "-":
                    workflow_name = workflow_name[1:]
                    sub_wf_presence = False
                sub_wf = test_patient.workflow.get_node(workflow_name)
                if not sub_wf_presence:
                    assert sub_wf is None, "There should not be %s subworkflow for %s" % (workflow_name, test_name)
                else:
                    assert sub_wf is not None, "Cannot find %s subworkflow for %s" % (workflow_name, test_name)
                    for node_name in this_test['check_nodes'][workflow_name]:
                        if type(node_name) is not list:
                            node_name = [node_name]
                        node_presence = True
                        if node_name[0][0] == "-":
                            node_name[0] = node_name[0][1:]
                            node_presence = False
                        node = sub_wf.get_node(node_name[0])
                        if not node_presence:
                            assert node is None, "There should not be %s in %s subworkflow for %s" % (node_name[0], workflow_name, test_name)
                        else:
                            assert node is not None, "Cannot find %s in %s subworkflow for %s" % (node_name[0], workflow_name, test_name)
                            if len(node_name) == 3:
                                assert hasattr(node.inputs, node_name[1]) is True, "No %s input in %s not in %s subworkflow for %s"  % (node_name[1], node_name[0], workflow_name, test_name)
                                input_value = getattr(node.inputs, node_name[1])
                                assert input_value == node_name[2], ("Error for %s input value (%s instead of %s) of %s node in subworkflow %s for %s" %
                                                                     (node_name[1], str(input_value), str(node_name[2]), node_name[0], workflow_name, test_name))

            if 'execute' in this_test and this_test['execute'] is True:
                self.last_node_cb = None
                self.allow_wf_errors = True
                cb = lambda report, tn=test_name: self.node_callback(report, tn)
                test_patient.start_workflow(True, True, update_node_callback=cb)
                qtbot.waitUntil(test_patient.workflow_process.stop_event.is_set, timeout=2000000)
                assert self.last_node_cb == WorkflowSignals.WORKFLOW_STOP, "Workflow finished but not segnaled"

            last_test = this_test

    def node_callback(self, wf_report: WorkflowReport, test_name: str):
        self.last_node_cb = wf_report.signal_type
        if not self.allow_wf_errors and wf_report.signal_type == WorkflowSignals.NODE_ERROR:
            assert False, "Node error during %s" % test_name

