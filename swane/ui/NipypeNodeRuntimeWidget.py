from PySide6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QPushButton, QTextEdit, QSpacerItem, QSizePolicy, QPlainTextEdit
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontMetrics
from swane import strings
from nipype.utils.filemanip import loadpkl
from datetime import datetime
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowSignals
from swane.ui.CustomTreeWidgetItem import CustomTreeWidgetItem
from multiprocessing import cpu_count
from nipype.interfaces.base.support import Bunch
from nipype.interfaces.base import traits
import math
import os
import subprocess


class NipypeNodeRuntimeWidget(QWidget):
    """
    Widget displaying runtime information for a Nipype node.
    Each row has a fixed minimum height to keep the UI consistent.
    """

    MIN_ROW_HEIGHT = 25  # minimum height in pixels for each row
    COMMAND_FILE_NAME = "command.txt"
    RESULT_FILE_NAME = "result_%s.pklz"
    NODE_FILE_NAME = "_node.pklz"
    IMAGE_EXTENSIONS = ('.nii', '.nii.gz', '.mgz', '.mgh')


    def __init__(self, slicer_path = None, parent=None):
        super().__init__(parent)

        # Create the grid layout
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.grid.setColumnStretch(6, 1)

        self._row = 0

        self.slicer_path = slicer_path

    def _open_in_slicer(self, path: str):
        """Open an image file in 3D Slicer."""
        if not path or not os.path.isfile(path):
            return

        if not self.slicer_path or not os.path.isfile(self.slicer_path):
            print("Slicer executable not found")
            return

        try:
            subprocess.Popen(
                [self.slicer_path, path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Failed to open in Slicer: {e}")


    # ------------------------------------------------------------------
    # Main method to load node results
    # ------------------------------------------------------------------

    def load_node_result(self, wf_base_dir: str, item: CustomTreeWidgetItem):
        """
        Update the UI based on available information.
        Shows only info that exists if the node is running.
        Read command from command.txt if result.pklz is not yet available.
        """
        node_parts = item.node_name.split(".")
        node_wf = node_parts[0]
        node_name = node_parts[1]

        node_dir = os.path.join(wf_base_dir, node_wf, node_name)

        self.clear()

        # ---------------- Node ----------------
        self._add_label(strings.sub_tab_node_name_label, self._row, 0)
        self._add_value(item.get_text(), self._row, 1, colspan=6)
        self._row += 1

        status = item.get_status()
        if status is None:
            self._add_label(strings.sub_tab_node_status_label, self._row, 0)
            self._add_value(strings.sub_tab_node_status_not_started, self._row, 1, colspan=6)
            self._row += 1

            self._add_spacer()

            return

        status_text = "—"
        crash_file = None
        node_pickle_file = os.path.join(node_dir, NipypeNodeRuntimeWidget.NODE_FILE_NAME)
        result_file = os.path.join(node_dir, NipypeNodeRuntimeWidget.RESULT_FILE_NAME % node_name)
        if status is WorkflowSignals.NODE_STARTED:
            if os.path.exists(node_pickle_file):
                start_ts = os.path.getctime(node_pickle_file)  # creation time in seconds
                start_time_str = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S")
                status_text = f"{strings.sub_tab_node_status_running} {start_time_str}"
        elif status is WorkflowSignals.NODE_COMPLETED:
            if os.path.exists(result_file):
                start_ts = os.path.getctime(result_file)  # creation time in seconds
                start_time_str = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S")
                status_text = f"{strings.sub_tab_node_status_completed} {start_time_str}"
        elif status is WorkflowSignals.NODE_ERROR:
            status_text = strings.sub_tab_node_status_failed
            crash_file = item.crash_file

        self._add_label(strings.sub_tab_node_status_label, self._row, 0)
        self._add_value(status_text, self._row, 1, colspan=6)
        self._row += 1

        # ---------------- Directory ----------------
        self._add_label(strings.sub_tab_node_dir_label, self._row, 0)
        if os.path.exists(node_dir):
            self._add_path_button(node_dir, self._row, 1)
        else:
            self._add_spacer()
            return
        self._row += 1

        # ---------------- Command ----------------
        self._add_label(strings.sub_tab_node_command_label, self._row, 0)

        command_txt = os.path.join(node_dir, NipypeNodeRuntimeWidget.COMMAND_FILE_NAME)
        command = None

        if os.path.exists(command_txt):
            with open(command_txt, "r") as f:
                command = f.read().strip()

        if command:
            cmd = QPlainTextEdit(command)
            cmd.setReadOnly(True)
            cmd.setLineWrapMode(QPlainTextEdit.WidgetWidth)
            cmd.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            cmd.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            font = cmd.font()
            font.setPointSize(font.pointSize() - 1)
            cmd.setFont(font)

            text_len = len(command)
            lines_needed = math.ceil(text_len / 75)
            fm = QFontMetrics(font)
            line_height = fm.lineSpacing()*lines_needed
            lines = max(1, command.count("\n") + 1)
            max_lines = 3
            visible_lines = min(lines, max_lines)

            # Consider document margin + extra padding
            margin = cmd.document().documentMargin()
            cmd.setFixedHeight(line_height * visible_lines + 2 * margin + 8)

            cmd.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            cmd.setStyleSheet("""
                QPlainTextEdit {
                    padding-top: 4px;
                    padding-bottom: 4px;
                }
            """)

            self.grid.addWidget(cmd, self._row, 1, 1, 6)

        else:
            self._add_value("—", self._row, 1, colspan=6)

        self._row += 1

        # ---------------- Crash (if it exists) ----------------
        if status is WorkflowSignals.NODE_ERROR and crash_file is not None and os.path.exists(crash_file):
            self._add_label(strings.sub_tab_node_crash_label, self._row, 0)
            self._add_path_button(crash_file, self._row, 1)
            self._row += 1

            self._add_spacer()
            return

        # ---------------- Result (if it exists) ----------------
        if status is WorkflowSignals.NODE_COMPLETED and os.path.exists(result_file):
            res = loadpkl(result_file)
            rt = res.runtime
            outputs = res.outputs

            # -------- Runtime info --------
            # Skip if node is MapNode
            is_mapnode = isinstance(rt, (list, tuple))
            if not is_mapnode:
                try:
                    # Assume rt.duration is in seconds (float)
                    seconds = int(rt.duration)  # drop decimals
                    minutes = seconds // 60
                    seconds = seconds % 60
                    formatted_duration = f"{minutes}m {seconds}s"
                    if minutes == 0:
                        formatted_duration = f"{seconds}s"
                    self._add_label(strings.sub_tab_node_duration_label, self._row, 0)
                    self._add_value(formatted_duration, self._row, 1)

                    self._add_label(strings.sub_tab_node_cpu_label, self._row, 2)
                    scaled_cpu_perc = rt.cpu_percent / cpu_count()
                    self._add_value(f"{scaled_cpu_perc:.1f}", self._row, 3)

                    self._add_label(strings.sub_tab_node_ram_label, self._row, 4)
                    self._add_value(f"{rt.mem_peak_gb:.3f}", self._row, 5)
                    self._row += 1
                except:
                    pass

            # -------- Outputs --------
            self._row += 1
            self._add_label(strings.sub_tab_node_output_label, self._row, 0)
            self._add_output_view(outputs, 1)


        self._add_spacer()

        return

    # ------------------------------------------------------------------
    # Helper functions
    # ------------------------------------------------------------------

    def clear(self):
        """Remove all widgets from the grid."""
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._row = 0

    def _add_spacer(self):
        # Add a vertical spacer at the end
        spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.grid.addItem(spacer, self._row, 0, 1, self.grid.columnCount())

    def _add_label(self, text, row, col):
        """Add a bold label to the grid."""
        label = QLabel(text)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet("font-weight: bold;")
        label.setMinimumHeight(self.MIN_ROW_HEIGHT)
        self.grid.addWidget(label, row, col)

    def _add_value(self, text, row, col, colspan=1):
        """Add a selectable value label to the grid."""
        label = QLabel(text)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMinimumHeight(self.MIN_ROW_HEIGHT)
        self.grid.addWidget(label, row, col, 1, colspan)

    def _add_output_row(self, name, value, row, col):
        """Add a single output row (label + value)."""

        # nome output
        name_lbl = QLabel(self._fmt_output_name(name))
        name_lbl.setMinimumHeight(self.MIN_ROW_HEIGHT)
        self.grid.addWidget(name_lbl, row, col)

        # valore
        if isinstance(value, str) and os.path.exists(value):
            self._add_path_button(value, row, col + 1)
        else:
            self._add_value(str(value), row, col + 1, colspan=5)

    def _add_path_button(self, path, row, col):
        is_image = (
                os.path.isfile(path)
                and path.lower().endswith(NipypeNodeRuntimeWidget.IMAGE_EXTENSIONS)
                and self.slicer_path is not None
                and os.path.isfile(self.slicer_path)
        )

        label = os.path.basename(path)

        btn = QPushButton(label)
        btn.setFlat(True)
        btn.setStyleSheet("text-align:left; color:#1a73e8;")
        btn.setMinimumHeight(self.MIN_ROW_HEIGHT)

        if is_image:
            btn.clicked.connect(
                lambda _, p=path: self._open_in_slicer(p)
            )
            btn.setToolTip("Open in 3D Slicer")
        else:
            print(1)
            btn.clicked.connect(
                lambda _, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(p))
            )

        self.grid.addWidget(btn, row, col, 1, 5)

    def _add_output_view(self, outputs, col):

        # -------------------------
        # Case 1: OutputSpec (Node)
        # -------------------------
        if hasattr(outputs, "traits"):
            for name, trait in outputs.traits().items():

                if trait.is_event or name.startswith("_"):
                    continue

                try:
                    value = getattr(outputs, name)
                except Exception:
                    continue

                if not self._is_valid_output_value(value):
                    continue

                if isinstance(value, (list, tuple)):
                    for v in value:
                        if self._is_valid_output_value(v):
                            self._add_output_row(name, v, self._row, col)
                            self._row += 1
                else:
                    self._add_output_row(name, value, self._row, col)
                    self._row += 1

        # -------------------------
        # Case 2: MapNode single iteration (Bunch)
        # -------------------------
        elif isinstance(outputs, Bunch):
            for key, value in outputs.items():

                if not self._is_valid_output_value(value):
                    continue

                if isinstance(value, (list, tuple)):
                    for v in value:
                        if self._is_valid_output_value(v):
                            self._add_output_row(key, v, self._row, col)
                            self._row += 1
                else:
                    self._add_output_row(key, value, self._row, col)
                    self._row += 1

        # -------------------------
        # Case 3: MapNode multiple iterations
        # -------------------------
        elif isinstance(outputs, (list, tuple)):
            for idx, bunch in enumerate(outputs):
                if not isinstance(bunch, Bunch):
                    continue

                # intestazione iterazione
                hdr = QLabel(f"[{idx}]")
                hdr.setStyleSheet("font-weight: bold;")
                self.grid.addWidget(hdr, self._row, col, 1, 6)
                self._row += 1

                for key, value in bunch.items():
                    if not self._is_valid_output_value(value):
                        continue

                    self._add_output_row(key, value, self._row, col)
                    self._row += 1

        # -------------------------
        # Case 4: Nothing usable
        # -------------------------
        else:
            self._add_value("—", self._row, col, colspan=6)

    def _is_valid_output_value(self, value):
        if value is None:
            return False
        if value is traits.Undefined:
            return False
        if value == "<undefined>":
            return False
        if value == "":
            return False
        if isinstance(value, (list, tuple)) and not value:
            return False
        return True

    def _fmt_output_name(self, name):
        return f"<i><u>{name}</u></i>"

