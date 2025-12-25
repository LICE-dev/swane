from PySide6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QPushButton, QTextEdit, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from swane import strings
from nipype.utils.filemanip import loadpkl
import os
from datetime import datetime
from swane.nipype_pipeline.engine.WorkflowReport import WorkflowSignals
from swane.ui.CustomTreeWidgetItem import CustomTreeWidgetItem
from multiprocessing import cpu_count
from nipype.interfaces.base.support import Bunch
from nipype.interfaces.base import traits


class NipypeNodeRuntimeWidget(QWidget):
    """
    Widget displaying runtime information for a Nipype node.
    Each row has a fixed minimum height to keep the UI consistent.
    """

    MIN_ROW_HEIGHT = 25  # minimum height in pixels for each row
    COMMAND_FILE_NAME = "command.txt"
    RESULT_FILE_NAME = "result_%s.pklz"
    NODE_FILE_NAME = "_node.pklz"

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create the grid layout
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        self.grid.setColumnStretch(6, 1)

        self._row = 0

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

        self._add_label(strings.sub_tab_node_status_label, self._row, 0)
        self._add_value(status_text, self._row, 1, colspan=6)
        self._row += 1

        # ---------------- Directory ----------------
        self._add_label(strings.sub_tab_node_dir_label, self._row, 0)
        if os.path.exists(node_dir):
            self._add_directory_button(node_dir, self._row, 1)
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
            cmd = QTextEdit(command)
            cmd.setReadOnly(True)
            cmd.setMaximumHeight(60)
            cmd.setMinimumHeight(self.MIN_ROW_HEIGHT * 2)
            cmd.setLineWrapMode(QTextEdit.WidgetWidth)
            cmd.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            cmd.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            cmd.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            font = QFont()
            font.setFamily("Monospace")
            font.setPointSize(font.pointSize() - 1)
            cmd.setFont(font)
            self.grid.addWidget(cmd, self._row, 1, 1, 6)
        else:
            self._add_value("—", self._row, 1, colspan=6)

        self._row += 1

        # ---------------- Result (if it exists) ----------------
        if os.path.exists(result_file):
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
            self._add_label(strings.sub_tab_node_output_label, self._row, 0)
            self._add_output_view(outputs, self._row, 1)
            self._row += 1

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

    def _add_directory_button(self, path, row, col):
        """Add a clickable directory button that opens in the system file manager."""
        if not path:
            self._add_value("—", row, col, colspan=6)
            return

        btn = QPushButton(path)
        btn.setFlat(True)
        btn.setStyleSheet("text-align:left; color:#1a73e8;")
        btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        )
        btn.setMinimumHeight(self.MIN_ROW_HEIGHT)
        self.grid.addWidget(btn, row, col, 1, 6)

    def _add_output_view(self, outputs, row, col):
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(self.MIN_ROW_HEIGHT * 4)

        lines = []

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
                            lines.append(f"{self._fmt_output_name(name)}: {v}")
                else:
                    lines.append(f"{self._fmt_output_name(name)}: {value}")

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
                            lines.append(f"{self._fmt_output_name(key)}: {v}")
                else:
                    lines.append(f"{self._fmt_output_name(key)}: {value}")

        # -------------------------
        # Case 3: MapNode multiple iterations
        # -------------------------
        elif isinstance(outputs, (list, tuple)):
            for idx, bunch in enumerate(outputs):
                if not isinstance(bunch, Bunch):
                    continue

                sub_lines = []
                for key, value in bunch.items():
                    if not self._is_valid_output_value(value):
                        continue
                    sub_lines.append(f"  {self._fmt_output_name(key)}: {value}")

                if sub_lines:
                    lines.append(f"[{idx}]")
                    lines.extend(sub_lines)

        # -------------------------
        # Case 4: Nothing usable
        # -------------------------
        else:
            pass

        text.setText("\n".join(lines) if lines else "—")
        self.grid.addWidget(text, row, col, 1, 6)

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

