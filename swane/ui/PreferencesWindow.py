import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QVBoxLayout, QGroupBox, QPushButton, QFileDialog, QMessageBox,
                               QHBoxLayout)

from swane import strings, EXIT_CODE_REBOOT
from swane.utils.ConfigManager import ConfigManager
from swane.utils.PreferenceEntry import PreferenceEntry
from swane.utils.DataInput import DataInputList


class PreferencesWindow(QDialog):

    def __init__(self, my_config, data_input_list=None, parent=None):
        super(PreferencesWindow, self).__init__(parent)

        self.my_config = my_config
        self.restart = False

        if self.my_config.global_config:
            title = strings.pref_window_title_global
        else:
            title = os.path.basename(os.path.dirname(
                self.my_config.config_file)) + strings.pref_window_title_user

        self.setWindowTitle(title)

        self.inputs = {}
        self.new_inputs = {}

        layout = QHBoxLayout()

        sn_pane = QGroupBox()
        sn_pane.setObjectName("sn_pane")
        sn_layout = QVBoxLayout()
        sn_pane.setLayout(sn_layout)
        sn_pane.setFlat(True)
        sn_pane.setStyleSheet("QGroupBox#sn_pane {border:none;}")

        middle_pane = QGroupBox()
        middle_pane.setObjectName("dx_pane")
        middle_pane.setFlat(True)
        middle_pane.setStyleSheet("QGroupBox#dx_pane {border:none;}")
        middle_layout = QVBoxLayout()
        middle_pane.setLayout(middle_layout)

        dx_pane = QGroupBox()
        dx_pane.setObjectName("dx_pane")
        dx_pane.setFlat(True)
        dx_pane.setStyleSheet("QGroupBox#dx_pane {border:none;}")
        dx_layout = QVBoxLayout()
        dx_pane.setLayout(dx_layout)

        x = 0
        if self.my_config.global_config:

            group_box1 = QGroupBox(strings.pref_window_global_box_title)
            grid1 = QGridLayout()
            group_box1.setLayout(grid1)
            x = 0

            category = "MAIN"

            self.new_inputs[x] = PreferenceEntry(category, 'patientsfolder', my_config, PreferenceEntry.DIRECTORY,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_mwd)
            self.new_inputs[x].set_box_text(strings.mainwindow_chose_working_dir_title)
            self.new_inputs[x].restart = True
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            grid1.addWidget(self.new_inputs[x].button, x, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'slicerPath', my_config, PreferenceEntry.FILE, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_slicer)
            self.new_inputs[x].set_box_text(strings.pref_window_select_slicer)
            self.new_inputs[x].restart = True
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            grid1.addWidget(self.new_inputs[x].button, x, 2)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'defaultWfType', my_config, PreferenceEntry.COMBO,
                                                 parent=self, populate_combo=ConfigManager.WORKFLOW_TYPES)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_wf)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'fmritaskduration', my_config, PreferenceEntry.NUMBER,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_task)
            self.new_inputs[x].set_range(1, 500)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'maxPt', my_config, PreferenceEntry.NUMBER, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_pt_limit)
            self.new_inputs[x].set_range(1, 5)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'maxPtCPU', my_config, PreferenceEntry.NUMBER, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_global_box_cpu_limit)
            self.new_inputs[x].set_range(-1, 40)
            grid1.addWidget(self.new_inputs[x].label, x, 0)
            grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            x += 1

            # Saving in MRML doesn't work well, disable extension choice for now
            # self.new_inputs[x] = PreferenceEntry(category, 'slicerSceneExt', my_config, PreferenceEntry.COMBO,
            #                                      parent=self, populate_combo=PreferencesWindow.SLICER_EXTENSIONS)
            # self.new_inputs[x].set_label_text(strings.pref_window_global_box_default_ext)
            # grid1.addWidget(self.new_inputs[x].label, x, 0)
            # grid1.addWidget(self.new_inputs[x].input_field, x, 1)
            # x += 1

            sn_layout.addWidget(group_box1)

            group_box_optional = QGroupBox(strings.pref_window_global_box_optional_title)
            grid_optional = QGridLayout()
            group_box_optional.setLayout(grid_optional)

            category = 'OPTIONAL_SERIES'
            data_input_list = DataInputList()

            for optional_series in my_config[category].keys():
                if optional_series not in data_input_list:
                    continue

                self.new_inputs[x] = PreferenceEntry(category, optional_series, my_config, PreferenceEntry.CHECKBOX,
                                                     parent=self)
                self.new_inputs[x].set_label_text(data_input_list[optional_series].label)
                self.new_inputs[x].restart = True
                grid_optional.addWidget(self.new_inputs[x].label, x, 0)
                grid_optional.addWidget(self.new_inputs[x].input_field, x, 1)
                x += 1

            sn_layout.addWidget(group_box_optional)

        else:
            group_box2 = QGroupBox(strings.pref_window_wf_box_title)
            grid2 = QGridLayout()
            group_box2.setLayout(grid2)

            self.my_config.update_freesurfer_pref()

            category = 'WF_OPTION'

            self.new_inputs[x] = PreferenceEntry(category, 'freesurfer', my_config, PreferenceEntry.CHECKBOX,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_wf_box_reconall)
            if not self.my_config.is_freesurfer():
                self.new_inputs[x].disable(strings.pref_window_wf_box_reconall_disabled_tip)
            self.new_inputs[x].input_field.stateChanged.connect(lambda checked, n=(x+1): self.freesurfer_changed(checked, n))
            grid2.addWidget(self.new_inputs[x].input_field, x, 0)
            grid2.addWidget(self.new_inputs[x].label, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'hippoAmygLabels', my_config, PreferenceEntry.CHECKBOX,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_wf_box_hippo)
            if not self.my_config.is_freesurfer_matlab() or not self.my_config.get_pt_wf_freesurfer():
                self.new_inputs[x].disable(strings.pref_window_wf_box_hippo_disabled_tip)
            grid2.addWidget(self.new_inputs[x].input_field, x, 0)
            grid2.addWidget(self.new_inputs[x].label, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'ai', my_config, PreferenceEntry.CHECKBOX, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_wf_box_ai)
            if not data_input_list[DataInputList.ASL].loaded and not data_input_list[DataInputList.PET].loaded:
                self.new_inputs[x].disable(strings.pref_window_wf_box_missing_ai)
            grid2.addWidget(self.new_inputs[x].input_field, x, 0)
            grid2.addWidget(self.new_inputs[x].label, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'domap', my_config, PreferenceEntry.CHECKBOX, parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_wf_box_domap)
            if not data_input_list[DataInputList.FLAIR3D].loaded:
                self.new_inputs[x].disable(strings.pref_window_wf_box_missing_flair3d)
            grid2.addWidget(self.new_inputs[x].input_field, x, 0)
            grid2.addWidget(self.new_inputs[x].label, x, 1)
            x += 1

            self.new_inputs[x] = PreferenceEntry(category, 'tractography', my_config, PreferenceEntry.CHECKBOX,
                                                 parent=self)
            self.new_inputs[x].set_label_text(strings.pref_window_wf_box_tractography)
            if not data_input_list[DataInputList.DTI].loaded:
                self.new_inputs[x].disable(strings.pref_window_wf_box_missing_dti)
            self.new_inputs[x].input_field.stateChanged.connect(self.tractography_changed)
            grid2.addWidget(self.new_inputs[x].input_field, x, 0)
            grid2.addWidget(self.new_inputs[x].label, x, 1)
            tract_x = x
            x += 1

            middle_layout.addWidget(group_box2)

            for y in range(DataInputList.FMRI_NUM):
                group_box_func = QGroupBox("fMRI - %d" % y)
                if not data_input_list[DataInputList.FMRI+'_%d' % y].loaded:
                    group_box_func.setEnabled(False)
                gridfunc = QGridLayout()
                group_box_func.setLayout(gridfunc)

                category = 'FMRI'

                opt_name = 'task_%d_name_a' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.TEXT,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_task_a_name)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 0)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 1)

                opt_name = 'task_%d_name_b' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.TEXT,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_task_b_name)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 2)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 3)
                x += 1

                opt_name = 'task_%d_duration' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.NUMBER,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_task_duration)
                self.new_inputs[opt_name].set_range(1, 500)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 0)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 1)

                opt_name = 'rest_%d_duration' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.NUMBER,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_rest_duration)
                self.new_inputs[opt_name].set_range(1, 500)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 2)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 3)
                x += 1

                opt_name = 'task_%d_tr' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.TEXT,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_tr)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 0)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 1)


                opt_name = 'task_%d_vols' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.TEXT,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_vols)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 2)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 3)
                x += 1

                opt_name = 'task_%d_blockdesign' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.COMBO,
                                                            parent=self, populate_combo=ConfigManager.BLOCK_DESIGNS)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_blockdesign)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 0)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 1)

                opt_name = 'task_%d_st' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.COMBO,
                                                            parent=self, populate_combo=ConfigManager.SLICE_TIMING)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_st)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 2)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 3)
                x += 1

                opt_name = 'task_%d_del_start_vols' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.NUMBER,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_del_start_vols)
                self.new_inputs[opt_name].set_range(0, 100)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 0)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 1)

                opt_name = 'task_%d_del_end_vols' % y
                self.new_inputs[opt_name] = PreferenceEntry(category, opt_name, my_config, PreferenceEntry.NUMBER,
                                                            parent=self)
                self.new_inputs[opt_name].set_label_text(strings.pref_window_fmri_box_del_end_vols)
                self.new_inputs[opt_name].set_range(0, 100)
                gridfunc.addWidget(self.new_inputs[opt_name].label, x, 2)
                gridfunc.addWidget(self.new_inputs[opt_name].input_field, x, 3)
                x += 1

                dx_layout.addWidget(group_box_func)

        self.group_box3 = QGroupBox(strings.pref_window_tract_box_title)
        grid3 = QGridLayout()
        self.group_box3.setLayout(grid3)
        if not self.my_config.global_config and (not data_input_list[DataInputList.DTI].loaded or not self.new_inputs[tract_x].input_field.isChecked()):
            self.group_box3.setEnabled(False)

        for index, key in enumerate(ConfigManager.TRACTS):
            self.new_inputs[x] = PreferenceEntry('DEFAULTTRACTS', key, my_config, PreferenceEntry.CHECKBOX, parent=self)
            self.new_inputs[x].set_label_text(ConfigManager.TRACTS[key][0])
            grid3.addWidget(self.new_inputs[x].input_field, x, 0)
            grid3.addWidget(self.new_inputs[x].label, x, 1)
            x += 1

        middle_layout.addWidget(self.group_box3)

        self.saveButton = QPushButton(strings.pref_window_save_button)
        self.saveButton.clicked.connect(self.save_preferences)

        discard_button = QPushButton("Discard changes")
        discard_button.clicked.connect(self.close)

        if self.my_config.global_config:
            layout.addWidget(sn_pane)
            sn_layout.addWidget(self.saveButton)
            sn_layout.addWidget(discard_button)
        layout.addWidget(middle_pane)
        if not self.my_config.global_config:
            middle_layout.addWidget(self.saveButton)
            middle_layout.addWidget(discard_button)
            layout.addWidget(dx_pane)

        self.setLayout(layout)

    def chose_dir(self, edit, message):
        folder_path = QFileDialog.getExistingDirectory(self, message)
        if not os.path.exists(folder_path):
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.NoIcon)
            msg_box.setText(strings.pref_window_dir_error)
            msg_box.exec()
            return
        edit.setText(folder_path)
        self.set_restart()

    def chose_file(self, edit, message):
        file_path, _ = QFileDialog.getOpenFileName(self, message)
        if not os.path.exists(file_path):
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.NoIcon)
            msg_box.setText(strings.pref_window_file_error)
            msg_box.exec()
            return
        edit.setText(file_path)
        self.set_restart()

    def freesurfer_changed(self, checked, hippo_index):
        if not checked or not self.my_config.is_freesurfer_matlab():
            self.new_inputs[hippo_index].disable()
        elif self.my_config.is_freesurfer_matlab():
            self.new_inputs[hippo_index].enable()

    def tractography_changed(self, checked):
        self.group_box3.setEnabled(checked)

    @staticmethod
    def set_checkbox(checkbox, value):
        if value:
            checkbox.setCheckState(Qt.Checked)
        else:
            checkbox.setCheckState(Qt.Unchecked)

    def set_restart(self):
        self.restart = True
        self.saveButton.setText(strings.pref_window_save_restart_button)

    def save_preferences(self):

        for pref_entry in self.new_inputs.values():
            if pref_entry.changed:
                self.my_config[pref_entry.category][pref_entry.key] = pref_entry.get_value()

        self.my_config.save()

        if self.restart:
            ret_code = EXIT_CODE_REBOOT
        else:
            ret_code = 1

        self.done(ret_code)
