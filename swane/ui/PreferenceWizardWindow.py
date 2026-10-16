from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QStackedWidget,
    QWidget,
    QPushButton,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QCheckBox,
    QComboBox,
    QSpinBox,
    QMessageBox,
)

from swane.resources import strings
from swane.config.ConfigManager import ConfigManager
from swane.config import dependency_policy
from swane.config.config_enums import (
    FreesurferStep,
    GlobalPrefCategoryList,
    PerformanceProfile,
    RegistrationEngine,
    DeskullEngine,
    TractographyEngine,
    SegmentationEngine,
    FmriEngine,
)
from swane.config.preference_list import GLOBAL_PREFERENCES, WF_PREFERENCES
from swane.config.PreferenceEntry import PreferenceEntry
from swane.utils.DataInputList import DataInputList
from swane.utils.ResourceManager import ResourceManager
from swane.utils.DependencyManager import DependencyManager
from swane.utils.platform_and_tools_utils import is_mac, is_windows

#: Engine preferences (GlobalPrefCategoryList.SYNTH) the wizard lets the user
#: choose, each with its options in order of recommendation. The default engine
#: of the active dependency policy (see dependency_policy.default_engines) is
#: always recommended first; the FreeSurfer Synth options are not recommended
#: on macOS, where they need much more RAM.
ENGINE_PREFERENCE_ORDER = {
    "deskull_engine": [
        DeskullEngine.ANTSPYNET,
        DeskullEngine.SYNTHSTRIP,
        DeskullEngine.BET,
    ],
    "engine": [
        RegistrationEngine.ANTS,
        RegistrationEngine.SYNTH,
        RegistrationEngine.FSL,
    ],
    "tractography_engine": [
        TractographyEngine.DIPY_RECOBUNDLES,
        TractographyEngine.FSL_XTRACT,
    ],
    "segmentation_engine": [SegmentationEngine.ANTS, SegmentationEngine.FSL],
    "fmri_engine": [FmriEngine.NILEARN, FmriEngine.FSL],
}
SYNTH_ENGINE_OPTIONS = {DeskullEngine.SYNTHSTRIP, RegistrationEngine.SYNTH}

#: Resource levels, from the lightest to the heaviest, with their description.
RESOURCE_LEVELS = [
    (PerformanceProfile.LOW_RESOURCE, strings.performance_profile_min_tooltip),
    (PerformanceProfile.BALANCED, strings.performance_profile_balanced_tooltip),
    (PerformanceProfile.MAX_PERF, strings.performance_profile_max_tooltip),
]


@dataclass
class UserPreferences:
    """
    Container for the choices collected by the configuration wizard.

    On the first run the choices start from the recommendations for this
    computer; on later runs they start from the current configuration.

    Attributes
    ----------
    performance_profile : PerformanceProfile
        Share of this computer SWANe can use.
    parallel_subjects : int
        Subjects analysed at the same time, sharing the profile resources.
    gpu_capable : bool
        Whether the current system appears to support GPU/CUDA acceleration.
    use_gpu_acceleration : bool
        GPU acceleration preference (only meaningful if gpu_capable).
    engines : dict
        Engine preference key -> chosen enum member.
    synth_capable : bool
        Whether the installed FreeSurfer provides the Synth tools.
    use_synth_freesurfer : bool
        Use SynthSeg / Synth recon-all for the FreeSurfer analyses.
    freesurfer_capable, matlab_capable : bool
        Whether FreeSurfer and its Matlab runtime are detected.
    cortical_parcellation_enabled, surfaces_enabled,
    hippocampal_segmentation_enabled, full_reconall_enabled : bool
        FreeSurfer outputs selection.

    """

    performance_profile: PerformanceProfile = PerformanceProfile.BALANCED
    parallel_subjects: int = 1

    gpu_capable: bool = False
    use_gpu_acceleration: bool = False

    engines: dict = field(default_factory=dict)

    synth_capable: bool = False
    use_synth_freesurfer: bool = False

    freesurfer_capable: bool = False
    matlab_capable: bool = False
    cortical_parcellation_enabled: bool = False
    surfaces_enabled: bool = False
    hippocampal_segmentation_enabled: bool = False
    full_reconall_enabled: bool = False


@dataclass
class WizardPlan:
    """
    Settings the wizard resolves from the user choices, the detected tools
    and the resources of the chosen profile.

    The same plan is shown on the Review page and written by
    `PreferenceWizardWindow._apply_settings_config`, so the review always
    matches what is applied.

    Attributes
    ----------
    resources : dict
        PERFORMANCE preferences set by the profile (ram_gb, max_subj_cpu,
        max_subj), see ConfigManager.get_resource_profile_values.
    cuda : bool
        CUDA preference.
    engines : dict
        Engine preference key -> selected enum member.
    engine_notes : dict
        Engine preference key -> review note for an engine selected although
        its RAM requirement or its tools are not met (no option fits).
    synth_reconall : bool
        Use Synth tools during recon-all.
    freesurfer_step : FreesurferStep
        Default 3D T1w FreeSurfer step.
    hippo_amyg_labels : bool
        Default hippocampal/amygdala subfields segmentation.

    """

    resources: dict
    cuda: bool = False
    engines: dict = field(default_factory=dict)
    engine_notes: dict = field(default_factory=dict)
    synth_reconall: bool = False
    freesurfer_step: FreesurferStep = FreesurferStep.DISABLED
    hippo_amyg_labels: bool = False

    @property
    def ram_gb(self) -> float:
        return float(self.resources["ram_gb"])


class PreferenceWizardWindow(QDialog):
    """
    Wizard dialog for selecting SWANe configuration preferences.

    The wizard guides the user through a multi-step configuration flow:
    1) Welcome
    2) Computer share: how much RAM/CPU SWANe can use, split among the
       subjects analysed at the same time
    3) Hardware acceleration selection (only if GPU/CUDA capable)
    4) Processing engines, restricted to the installed tools that fit the RAM
       of each subject
    5) FreeSurfer outputs selection (only if FreeSurfer is detected)
    6) Review summary
    7) Configuration applied

    Parameters
    ----------
    global_config : ConfigManager
        SWANe global configuration, updated and saved when the user applies.
    dependency_manager : DependencyManager
        SWANe dependency manager used to check the installed tools.
    first_run : bool, optional
        If True the choices start from the recommendations for this computer,
        otherwise from the current configuration. Default is False.
    parent : QWidget, optional
        Parent widget.

    Attributes
    ----------
    global_config : ConfigManager
        Stored configuration object passed to the constructor.
    dependency_manager : DependencyManager
        Stored dependency manager passed to the constructor.
    first_run : bool
        Whether the wizard started from the recommendations.
    user_prefs : UserPreferences
        The in-memory container of user choices collected by the wizard.

    """

    def __init__(
        self,
        global_config: ConfigManager,
        dependency_manager: DependencyManager,
        first_run: bool = False,
        parent=None,
    ):
        super(PreferenceWizardWindow, self).__init__(parent)

        self.global_config: ConfigManager = global_config
        self.dependency_manager: DependencyManager = dependency_manager
        self.first_run = first_run
        self.user_prefs = UserPreferences()

        self.setWindowTitle(strings.preference_wizard_title)
        self.setModal(True)

        self._stack = QStackedWidget()
        self._pages = []

        # Nav buttons
        self._back_btn = QPushButton(strings.wizard_back_button)
        self._next_btn = QPushButton(strings.wizard_next_button)
        self._finish_btn = QPushButton(strings.wizard_finish_button)
        self._cancel_btn = QPushButton(strings.wizard_cancel_button)

        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        self._finish_btn.clicked.connect(self._finish)
        self._cancel_btn.clicked.connect(self.reject)

        root = QVBoxLayout()
        root.addWidget(self._stack)

        nav = QHBoxLayout()
        nav.addWidget(self._back_btn)
        nav.addWidget(self._next_btn)
        nav.addStretch(1)
        nav.addWidget(self._finish_btn)
        nav.addWidget(self._cancel_btn)
        root.addLayout(nav)

        self.setLayout(root)

        # Capability detection
        self.user_prefs.gpu_capable = ResourceManager.is_cuda()
        self.user_prefs.synth_capable = bool(
            self.dependency_manager.is_freesurfer_synth()
        )
        self.user_prefs.freesurfer_capable = self.dependency_manager.is_freesurfer()
        self.user_prefs.matlab_capable = self.dependency_manager.is_freesurfer_matlab()

        self._load_initial_choices()

        # Build wizard flow
        self._build_pages()
        self._sync_ui()

    # --------------------------
    # Initial choices
    # --------------------------

    def _load_initial_choices(self) -> None:
        """
        Fills `user_prefs` with the recommendations (first run) or with the
        current configuration (later runs).

        Returns
        -------
        None.

        """

        prefs = self.user_prefs

        if self.first_run:
            prefs.performance_profile = PerformanceProfile.BALANCED
            prefs.parallel_subjects = 1
            prefs.use_gpu_acceleration = prefs.gpu_capable
            prefs.use_synth_freesurfer = prefs.synth_capable and not is_mac()
            ram_gb = self._resources()["ram_gb"]
            prefs.engines = {
                key: self._select_engine(key, ram_gb)[0]
                for key in ENGINE_PREFERENCE_ORDER
            }
            return

        config = self.global_config
        perf = GlobalPrefCategoryList.PERFORMANCE
        ram_gb = config.getfloat_safe(perf, "ram_gb")
        max_subj = max(1, config.get_max_subject_tabs())

        # Closest resource level to the current total RAM allocation
        current_total = ram_gb * max_subj
        prefs.performance_profile = min(
            (level for level, _ in RESOURCE_LEVELS),
            key=lambda level: abs(
                ConfigManager.get_resource_budget(level)[0] - current_total
            ),
        )
        prefs.parallel_subjects = min(max_subj, ResourceManager.MAX_PARALLEL_SUBJECTS)

        prefs.use_gpu_acceleration = prefs.gpu_capable and config.getboolean_safe(
            perf, "cuda"
        )

        prefs.engines = {
            key: config.getenum_safe(GlobalPrefCategoryList.SYNTH, key)
            for key in ENGINE_PREFERENCE_ORDER
        }

        step = config.getenum_safe(DataInputList.T13D, "freesurfer_step")
        prefs.full_reconall_enabled = step is FreesurferStep.RECONALL
        prefs.surfaces_enabled = step is FreesurferStep.AUTORECON_PIAL
        prefs.cortical_parcellation_enabled = step in (
            FreesurferStep.SYNTHSEG,
            FreesurferStep.AUTORECON_PIAL,
        )
        prefs.hippocampal_segmentation_enabled = (
            prefs.matlab_capable
            and step.has_surface()
            and config.getboolean_safe(DataInputList.T13D, "hippo_amyg_labels")
        )
        prefs.use_synth_freesurfer = prefs.synth_capable and (
            step is FreesurferStep.SYNTHSEG
            or config.getboolean_safe(GlobalPrefCategoryList.SYNTH, "reconall")
        )

    # --------------------------
    # Pages builder
    # --------------------------

    def _build_pages(self) -> None:
        """
        Builds and registers all wizard pages according to the current environment.

        The Hardware Acceleration page is added only when the system is detected as
        GPU/CUDA capable.
        The Freesurfer Outputs page is added only when FreeSurfer is detected.

        Returns
        -------
        None.

        """

        self._add_page(self._page_welcome())
        self._add_page(self._page_resources())

        if self.user_prefs.gpu_capable:
            self._add_page(self._page_hardware_acceleration())

        self._add_page(self._page_engines())

        if self.user_prefs.freesurfer_capable:
            self._add_page(self._page_freesurfer_outputs())

        self._add_page(self._page_review())
        self._add_page(self._page_applied())

        self._stack.setCurrentIndex(0)

    def _add_page(self, page: QWidget) -> None:
        """
        Adds a wizard page to the internal page list and the stacked widget.

        Parameters
        ----------
        page : QWidget
            Page widget to be added to the wizard flow.

        Returns
        -------
        None.

        """

        self._pages.append(page)
        self._stack.addWidget(page)

    def _make_title(self, title: str, body: str) -> tuple[QWidget, QLabel]:
        """
        Creates a standardized title/header widget for wizard pages.

        Parameters
        ----------
        title : str
            Page title text.
        body : str
            Page description text.

        Returns
        -------
        tuple
            A widget containing the formatted page header and its body label.

        """

        w = QWidget()
        lay = QVBoxLayout()
        t = QLabel(title)
        t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        t.setStyleSheet("font-size: 18px; font-weight: 600;")
        b = QLabel(body)
        b.setWordWrap(True)
        b.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextBrowserInteraction)
        b.setOpenExternalLinks(True)

        lay.addWidget(t)
        lay.addWidget(b)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)

        w.setLayout(lay)
        return w, b

    # --------------------------
    # Page: Welcome
    # --------------------------

    def _page_welcome(self) -> QWidget:
        """
        Creates the Welcome/Intro wizard page.

        Returns
        -------
        QWidget
            The constructed Welcome page widget.

        """

        page = QWidget()
        lay = QVBoxLayout()
        welcome_text = strings.wizard_welcome_text
        if is_windows():
            welcome_text += "<br><br>" + strings.windows_experimental_warn
        lay.addWidget(self._make_title(strings.wizard_welcome_title, welcome_text)[0])

        lay.addStretch(1)
        page.setLayout(lay)

        # Custom Attribute to rename Next button
        page._wizard_next_label = strings.wizard_start_button  # type: ignore[attr-defined]
        return page

    # --------------------------
    # Page: Computer share
    # --------------------------

    def _page_resources(self) -> QWidget:
        """
        Creates the page that asks how much of this computer SWANe can use.

        The user picks one of three resource levels (each showing the RAM and
        CPU cores it allows) and how many subjects are analysed at the same
        time. The level resources are split among those subjects, so all the
        subject tabs together never exceed the chosen share.

        Returns
        -------
        QWidget
            The constructed page widget.

        """

        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(
            self._make_title(
                strings.wizard_performance_title,
                strings.wizard_performance_text.format(
                    ram_gb=ResourceManager.total_memory_gb(),
                    cpu=ResourceManager.get_max_cpu(),
                ),
            )[0]
        )

        self._perf_group = QButtonGroup(self)
        self._perf_buttons = {}
        for level, tooltip in RESOURCE_LEVELS:
            ram_gb, cpu = ConfigManager.get_resource_budget(level)
            button = QRadioButton(
                strings.wizard_resource_level.format(
                    name=level.value, ram_gb=ram_gb, cpu=cpu, tooltip=tooltip
                )
            )
            self._perf_group.addButton(button)
            self._perf_buttons[level] = button
            lay.addWidget(button)

        parallel_row = QHBoxLayout()
        parallel_row.addWidget(QLabel(strings.wizard_parallel_subjects))
        self._parallel_spin = QSpinBox()
        self._parallel_spin.setMinimum(1)
        parallel_row.addWidget(self._parallel_spin)
        parallel_row.addStretch(1)
        lay.addSpacing(8)
        lay.addLayout(parallel_row)

        self._parallel_spin.setMaximum(ResourceManager.MAX_PARALLEL_SUBJECTS)

        self._per_subject_label = QLabel("")
        self._per_subject_label.setWordWrap(True)
        self._per_subject_label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self._per_subject_label)

        self._low_ram_label = QLabel("")
        self._low_ram_label.setWordWrap(True)
        self._low_ram_label.setStyleSheet("color: #c0392b;")
        lay.addWidget(self._low_ram_label)

        if not self.first_run:
            current = QLabel(self._current_resources_text())
            current.setWordWrap(True)
            current.setTextFormat(Qt.TextFormat.RichText)
            lay.addSpacing(8)
            lay.addWidget(current)

        lay.addStretch(1)
        page.setLayout(lay)

        self._perf_buttons[self.user_prefs.performance_profile].setChecked(True)
        self._set_performance_profile(self.user_prefs.performance_profile)
        for level, button in self._perf_buttons.items():
            button.toggled.connect(
                lambda checked, my_level=level: checked
                and self._set_performance_profile(my_level)
            )
        self._parallel_spin.valueChanged.connect(self._set_parallel_subjects)

        return page

    def _current_resources_text(self) -> str:
        """
        Describes the current resource configuration.

        Returns
        -------
        str
            Rich text description.

        """

        perf = GlobalPrefCategoryList.PERFORMANCE
        ram_gb = self.global_config.getfloat_safe(perf, "ram_gb")
        cpu = self.global_config.getint_safe(perf, "max_subj_cpu")
        if cpu < 1:
            cpu = ResourceManager.get_max_cpu()
        max_subj = max(1, self.global_config.get_max_subject_tabs())
        return strings.wizard_current_resources.format(
            ram_gb=ram_gb, cpu=cpu, max_subj=max_subj
        )

    def _set_performance_profile(self, profile: PerformanceProfile) -> None:
        """
        Stores the chosen resource level.

        Parameters
        ----------
        profile : PerformanceProfile
            The chosen resource level.

        Returns
        -------
        None.

        """

        self.user_prefs.performance_profile = profile
        self._parallel_spin.blockSignals(True)
        self._parallel_spin.setValue(self.user_prefs.parallel_subjects)
        self._parallel_spin.blockSignals(False)
        self._set_parallel_subjects(self._parallel_spin.value())

    def _set_parallel_subjects(self, value: int) -> None:
        """
        Stores the parallel subjects and refreshes the per-subject resources.
        Adding a subject that brings the RAM per subject below
        ResourceManager.LOW_SUBJECT_RAM_GB raises an alert.

        Parameters
        ----------
        value : int
            Subjects analysed at the same time.

        Returns
        -------
        None.

        """

        previous_ram = float(self._resources()["ram_gb"])
        added = int(value) > self.user_prefs.parallel_subjects
        self.user_prefs.parallel_subjects = int(value)
        resources = self._resources()
        ram_gb = float(resources["ram_gb"])
        self._per_subject_label.setText(
            strings.wizard_per_subject_resources.format(
                ram_gb=ram_gb, cpu=resources["max_subj_cpu"]
            )
        )

        low_ram = ram_gb < ResourceManager.LOW_SUBJECT_RAM_GB
        warning = (
            strings.low_subject_ram_warning.format(
                subjects=resources["max_subj"],
                ram_gb=ram_gb,
                limit=ResourceManager.LOW_SUBJECT_RAM_GB,
            )
            if low_ram
            else ""
        )
        self._low_ram_label.setText(warning)
        self._low_ram_label.setVisible(low_ram)
        if low_ram and added and ram_gb < previous_ram:
            self._alert_low_subject_ram(warning)

    def _alert_low_subject_ram(self, warning: str) -> None:
        """
        Alerts that the RAM per subject fell below
        ResourceManager.LOW_SUBJECT_RAM_GB.

        Parameters
        ----------
        warning : str
            The alert text.

        Returns
        -------
        None.

        """

        QMessageBox.warning(self, strings.low_subject_ram_title, warning)

    def _resources(self) -> dict:
        """
        Returns
        -------
        dict
            The PERFORMANCE preferences of the current resource choice.

        """

        return ConfigManager.get_resource_profile_values(
            self.user_prefs.performance_profile, self.user_prefs.parallel_subjects
        )

    # --------------------------
    # Page: Hardware Acceleration (optional)
    # --------------------------

    def _page_hardware_acceleration(self) -> QWidget:
        """
        Creates the Hardware Acceleration selection wizard page.

        This page is only added to the wizard flow when the system is detected as
        GPU/CUDA capable.

        Returns
        -------
        QWidget
            The constructed Hardware Acceleration page widget.

        """

        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(
            self._make_title(
                strings.wizard_hardware_accelleration_title,
                strings.wizard_hardware_accelleration_text,
            )[0]
        )

        self._gpu_group = QButtonGroup(self)

        rb_gpu = QRadioButton(
            strings.gpu_acceleration_enabled
            + "\n"
            + strings.gpu_acceleration_enabled_tooltip
        )
        rb_cpu = QRadioButton(
            strings.gpu_acceleration_disabled
            + "\n"
            + strings.gpu_acceleration_disabled_tooltip
        )

        self._gpu_group.addButton(rb_gpu, 1)
        self._gpu_group.addButton(rb_cpu, 0)

        lay.addWidget(rb_gpu)
        lay.addWidget(rb_cpu)
        lay.addStretch(1)
        page.setLayout(lay)

        if self.user_prefs.use_gpu_acceleration:
            rb_gpu.setChecked(True)
        else:
            rb_cpu.setChecked(True)
        self._gpu_group.idToggled.connect(
            lambda button_id, checked: checked
            and setattr(self.user_prefs, "use_gpu_acceleration", bool(button_id))
        )

        return page

    # --------------------------
    # Page: Processing engines
    # --------------------------

    def _page_engines(self) -> QWidget:
        """
        Creates the Processing Engines wizard page.

        One combo box per engine preference. Options whose tools are not
        installed or that need more RAM than each subject can use are disabled,
        with the reason as tooltip; the page is refreshed every time it is
        entered, since the RAM per subject depends on the resources page.

        Returns
        -------
        QWidget
            The constructed Processing Engines page widget.

        """

        page = QWidget()
        lay = QVBoxLayout()
        title, self._engines_text = self._make_title(strings.wizard_engines_title, "")
        lay.addWidget(title)

        grid = QGridLayout()
        self._engine_combos: dict[str, QComboBox] = {}
        self._engine_notes: dict[str, QLabel] = {}
        for row, key in enumerate(ENGINE_PREFERENCE_ORDER):
            entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key]
            combo = QComboBox()
            for option in entry.value_enum:
                combo.addItem(option.value, userData=option)
            note = QLabel(strings.wizard_engine_no_option)
            note.setStyleSheet("color: #c0392b;")
            note.setWordWrap(True)
            note.hide()
            grid.addWidget(QLabel(entry.label), 2 * row, 0)
            grid.addWidget(combo, 2 * row, 1)
            grid.addWidget(note, 2 * row + 1, 1)
            self._engine_combos[key] = combo
            self._engine_notes[key] = note
            combo.currentIndexChanged.connect(
                lambda index, my_key=key, my_combo=combo: self._set_engine(
                    my_key, my_combo.itemData(index)
                )
            )
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        recommended = QPushButton(strings.wizard_engines_recommended_button)
        recommended.clicked.connect(self._use_recommended_engines)
        rec_row = QHBoxLayout()
        rec_row.addWidget(recommended)
        rec_row.addStretch(1)
        lay.addSpacing(8)
        lay.addLayout(rec_row)

        lay.addStretch(1)
        page.setLayout(lay)

        page._wizard_on_enter = self._refresh_engine_page  # type: ignore[attr-defined]
        return page

    def _set_engine(self, key: str, option: Optional[Enum]) -> None:
        if option is not None:
            self.user_prefs.engines[key] = option

    def _engine_option_status(
        self, key: str, option: Enum, ram_gb: float
    ) -> tuple[bool, str]:
        """
        Checks whether an engine option can be selected.

        Parameters
        ----------
        key : str
            The engine preference key.
        option : Enum
            The option.
        ram_gb : float
            RAM per subject.

        Returns
        -------
        tuple
            Whether the option is selectable and, if not, why.

        """

        entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key]
        if not self._is_option_available(entry, option, ram_gb, check_ram=False):
            return False, strings.wizard_engine_unavailable_tools.format(
                reason=entry.option_dependency[option][1]
            )
        if not self._is_option_available(entry, option, ram_gb):
            return False, strings.wizard_engine_unavailable_ram.format(
                ram=self._ram_requirement(entry, option) or 0
            )
        return True, ""

    def _refresh_engine_page(self) -> None:
        """
        Enables the engine options that fit the current RAM per subject and
        replaces a choice that no longer fits with the recommended engine.

        Returns
        -------
        None.

        """

        ram_gb = float(self._resources()["ram_gb"])
        self._engines_text.setText(strings.wizard_engines_text.format(ram_gb=ram_gb))
        for key, combo in self._engine_combos.items():
            model = combo.model()
            for index in range(combo.count()):
                enabled, reason = self._engine_option_status(
                    key, combo.itemData(index), ram_gb
                )
                item = model.item(index)
                item.setEnabled(enabled)
                item.setToolTip(reason)

            choice, note = self._resolve_engine(key, ram_gb)
            self.user_prefs.engines[key] = choice
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(choice))
            combo.blockSignals(False)
            self._engine_notes[key].setVisible(bool(note))

    def _use_recommended_engines(self) -> None:
        """
        Selects the recommended engine for every engine preference.

        Returns
        -------
        None.

        """

        ram_gb = float(self._resources()["ram_gb"])
        for key in ENGINE_PREFERENCE_ORDER:
            self.user_prefs.engines[key] = self._select_engine(key, ram_gb)[0]
        self._refresh_engine_page()

    # --------------------------
    # Page: FreeSurfer Outputs
    # --------------------------

    def _page_freesurfer_outputs(self) -> QWidget:
        """
        Creates the FreeSurfer Outputs selection wizard page.

        The page allows choosing which FreeSurfer outputs SWANe should enable
        and, when the installed FreeSurfer provides them, whether to use the
        Synth tools (SynthSeg, Synth recon-all).

        Returns
        -------
        QWidget
            The constructed FreeSurfer Outputs page widget.
        """
        page = QWidget()
        lay = QVBoxLayout()

        lay.addWidget(
            self._make_title(
                strings.wizard_freesurfer_outputs_title,
                strings.wizard_freesurfer_outputs_tooltip,
            )[0]
        )

        def add_checkbox(text: str, tooltip: str, attribute: str) -> QCheckBox:
            checkbox = QCheckBox(f"{text}\n{tooltip}")
            checkbox.setChecked(getattr(self.user_prefs, attribute))
            checkbox.toggled.connect(
                lambda checked: setattr(self.user_prefs, attribute, bool(checked))
            )
            lay.addWidget(checkbox)
            return checkbox

        self._cb_freesurfer_cortical_parcellation = add_checkbox(
            strings.freesurfer_outputs_cortical_parcellation,
            strings.freesurfer_outputs_cortical_parcellation_tooltip,
            "cortical_parcellation_enabled",
        )
        self._cb_freesurfer_surfaces = add_checkbox(
            strings.freesurfer_outputs_surfaces,
            strings.freesurfer_outputs_surfaces_tooltip,
            "surfaces_enabled",
        )
        if self.user_prefs.matlab_capable:
            self._cb_freesurfer_hippocampal_segmentation = add_checkbox(
                strings.freesurfer_outputs_hippocampal_segmentation,
                strings.freesurfer_outputs_hippocampal_segmentation_tooltip,
                "hippocampal_segmentation_enabled",
            )
        self._cb_freesurfer_full_reconall = add_checkbox(
            strings.freesurfer_full_reconall,
            strings.freesurfer_full_reconall_tooltip,
            "full_reconall_enabled",
        )

        if self.user_prefs.synth_capable:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            lay.addWidget(line)
            self._cb_freesurfer_synth = add_checkbox(
                strings.freesurfer_synth,
                strings.freesurfer_synth_tooltip,
                "use_synth_freesurfer",
            )
            if is_mac():
                warn = QLabel(strings.wizard_advanced_models_macos_warn)
                warn.setWordWrap(True)
                lay.addWidget(warn)

        lay.addStretch(1)
        page.setLayout(lay)

        return page

    # --------------------------
    # Page: Review
    # --------------------------

    def _page_review(self) -> QWidget:
        """
        Creates the Review wizard page.

        Returns
        -------
        QWidget
            The constructed Review page widget.

        """

        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(
            self._make_title(strings.wizard_review_title, strings.wizard_review_text)[0]
        )

        self._review_label = QLabel("")
        self._review_label.setWordWrap(True)
        self._review_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        footer = QLabel(strings.wizard_review_tooltip)
        footer.setWordWrap(True)
        footer.setStyleSheet("color: #666;")

        lay.addWidget(self._review_label)
        lay.addStretch(1)
        lay.addWidget(footer)
        page.setLayout(lay)

        page._wizard_on_enter = self._update_review_page  # type: ignore[attr-defined]
        return page

    # --------------------------
    # Page: Applied
    # --------------------------

    def _page_applied(self) -> QWidget:
        """
        Creates the final "Configuration Applied" wizard page.

        Returns
        -------
        QWidget
            The constructed Applied page widget.

        """

        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(
            self._make_title(strings.wizard_applied_title, strings.wizard_applied_text)[
                0
            ]
        )
        lay.addStretch(1)
        page.setLayout(lay)

        return page

    # --------------------------
    # Review
    # --------------------------

    def _update_review_page(self) -> None:
        """
        Updates the Review page summary text.

        The summary is generated from the same `WizardPlan` that Apply writes.

        Returns
        -------
        None.

        """

        self._review_label.setTextFormat(Qt.TextFormat.RichText)

        plan = self._build_plan(self._resources())
        resources = plan.resources

        parts: list[str] = []

        parts.append(
            strings.wizard_selected_profile.format(
                profile=self.user_prefs.performance_profile.value
            )
            + "<br />"
            + strings.wizard_resources.format(
                total_gb=plan.ram_gb * int(resources["max_subj"]),
                machine_gb=ResourceManager.total_memory_gb(),
                max_subj=resources["max_subj"],
                ram_gb=plan.ram_gb,
                cpu=resources["max_subj_cpu"],
            )
        )

        if not self.user_prefs.gpu_capable:
            gpu_status = strings.wizard_status_not_available
        elif plan.cuda:
            gpu_status = strings.wizard_status_enabled
        else:
            gpu_status = strings.wizard_status_disabled
        parts.append(strings.wizard_gpu_accelleration.format(gpu_status=gpu_status))

        rows = []
        for key, engine in plan.engines.items():
            rows.append(
                strings.wizard_engine_row.format(
                    label=GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key].label,
                    engine=engine.value,
                )
                + plan.engine_notes.get(key, "")
            )
        parts.append(strings.wizard_engines.format(engines="<br />".join(rows)))

        if not self.user_prefs.freesurfer_capable:
            fs_out = strings.wizard_status_not_detected
        elif plan.freesurfer_step is FreesurferStep.DISABLED:
            fs_out = strings.wizard_status_disabled
        else:
            fs_out = plan.freesurfer_step.value
            if plan.hippo_amyg_labels:
                fs_out += strings.wizard_freesurfer_hippo_suffix
            if plan.synth_reconall and plan.freesurfer_step.has_surface():
                fs_out += strings.wizard_freesurfer_synth_suffix
        parts.append(strings.wizard_freesurfer_outputs.format(fs_outputs=fs_out))

        self._review_label.setText("<br /><br />".join(parts))

    # --------------------------
    # Navigation
    # --------------------------

    def _enter_current_page(self) -> None:
        """
        Runs the refresh hook of the page just shown, if any.

        Returns
        -------
        None.

        """

        on_enter = getattr(self._stack.currentWidget(), "_wizard_on_enter", None)
        if on_enter is not None:
            on_enter()

    def _go_back(self) -> None:
        """
        Navigates to the previous wizard page.

        Returns
        -------
        None.

        """

        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._enter_current_page()
            self._sync_ui()

    def _go_next(self) -> None:
        """
        Navigates to the next wizard page.

        Returns
        -------
        None.

        """

        idx = self._stack.currentIndex()
        if idx < self._stack.count() - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._enter_current_page()
            self._sync_ui()

    def _finish(self) -> None:
        """
        Handles the Finish/Apply action depending on the current wizard page.

        Behavior:
        - On the Review page: applies the settings and moves to the final
          "Applied" page.
        - On the Applied page: closes the dialog with `accept()`.
        - On any other page: behaves like "Next".

        Returns
        -------
        None.

        """

        if self._is_review_page():
            self._apply_settings_config()
            self._stack.setCurrentIndex(self._stack.count() - 1)
            self._sync_ui()
            return

        if self._is_applied_page():
            self.accept()
            return

        self._go_next()

    def _is_review_page(self) -> bool:
        """
        Returns
        -------
        bool
            True if the current page is the Review page, False otherwise.

        """

        return self._stack.currentWidget() is self._pages[-2]

    def _is_applied_page(self) -> bool:
        """
        Returns
        -------
        bool
            True if the current page is the Applied page, False otherwise.

        """

        return self._stack.currentWidget() is self._pages[-1]

    def _sync_ui(self) -> None:
        """
        Synchronizes navigation button state and labels with the current wizard page.

        Returns
        -------
        None.

        """

        idx = self._stack.currentIndex()
        last = self._stack.count() - 1

        self._back_btn.setEnabled(idx > 0)

        w = self._stack.currentWidget()
        next_label = getattr(w, "_wizard_next_label", strings.wizard_next_button)
        self._next_btn.setText(next_label)

        if self._is_applied_page():
            self._next_btn.setEnabled(False)
            self._finish_btn.setEnabled(True)
            self._finish_btn.setText(strings.wizard_finish_button)
            self._back_btn.setEnabled(False)
            return

        if self._is_review_page():
            self._next_btn.setEnabled(False)
            self._finish_btn.setEnabled(True)
            self._finish_btn.setText(strings.wizard_apply_button)
            return

        self._next_btn.setEnabled(idx < last)
        self._finish_btn.setEnabled(False)
        self._finish_btn.setText(strings.wizard_finish_button)

    # --------------------------
    # Settings resolution
    # --------------------------

    def _is_option_available(
        self,
        entry: PreferenceEntry,
        option: Enum,
        ram_gb: float,
        check_ram: bool = True,
    ) -> bool:
        """
        Checks an enum preference option against its `PreferenceEntry`
        metadata, the same metadata the Preferences window enforces.

        Parameters
        ----------
        entry : PreferenceEntry
            The enum preference metadata.
        option : Enum
            The option to check.
        ram_gb : float
            RAM allocated per subject that the option must fit in.
        check_ram : bool
            If False, only the external dependency of the option is checked.

        Returns
        -------
        bool
            True if the option dependency is met and, when checked, its
            requirements are met. Requirements other than the RAM allocation
            fail closed.

        """

        if option in entry.option_dependency:
            dep_check = getattr(
                self.dependency_manager, entry.option_dependency[option][0], None
            )
            if dep_check is None or not callable(dep_check) or not dep_check():
                return False

        if not check_ram:
            return True

        for category, requirements in entry.option_pref_requirement.get(
            option, {}
        ).items():
            for key, threshold in requirements:
                if category != GlobalPrefCategoryList.PERFORMANCE or key != "ram_gb":
                    return False
                if ram_gb < threshold:
                    return False
        return True

    @staticmethod
    def _ram_requirement(entry: PreferenceEntry, option: Enum) -> Optional[float]:
        """
        Returns the RAM requirement declared for an enum preference option.

        Parameters
        ----------
        entry : PreferenceEntry
            The enum preference metadata.
        option : Enum
            The option.

        Returns
        -------
        float or None
            The minimum RAM per subject, None if the option declares none.

        """

        for key, threshold in entry.option_pref_requirement.get(option, {}).get(
            GlobalPrefCategoryList.PERFORMANCE, []
        ):
            if key == "ram_gb":
                return threshold
        return None

    def _engine_candidates(self, key: str) -> list:
        """
        Options of an engine preference in order of recommendation: the
        policy default first, the Synth options left out on macOS.

        Parameters
        ----------
        key : str
            The engine preference key.

        Returns
        -------
        list
            The enum members.

        """

        default = dependency_policy.default_engines(dependency_policy.FSL_MANDATORY)[
            key
        ]
        candidates = [default] + [
            option for option in ENGINE_PREFERENCE_ORDER[key] if option != default
        ]
        if is_mac():
            candidates = [
                option for option in candidates if option not in SYNTH_ENGINE_OPTIONS
            ]
        return candidates

    def _select_engine(self, key: str, ram_gb: float) -> tuple[Enum, str]:
        """
        Recommends the option of an engine preference.

        The first candidate (see `_engine_candidates`) whose tools are
        installed and whose RAM requirement fits is selected. If none fits,
        the first candidate whose tools are installed is selected anyway (and
        flagged in the review), and if no candidate has its tools installed
        the policy default is kept.

        Parameters
        ----------
        key : str
            The engine preference key in GlobalPrefCategoryList.SYNTH.
        ram_gb : float
            RAM allocated per subject.

        Returns
        -------
        tuple
            The selected enum member and its review note ("" if it fits).

        """

        entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key]
        candidates = self._engine_candidates(key)
        for option in candidates:
            if self._is_option_available(entry, option, ram_gb):
                return option, ""

        for option in candidates:
            if self._is_option_available(entry, option, ram_gb, check_ram=False):
                ram = self._ram_requirement(entry, option)
                return option, (
                    strings.wizard_engine_low_ram.format(ram=ram) if ram else ""
                )

        default = dependency_policy.default_engines(dependency_policy.FSL_MANDATORY)[
            key
        ]
        return default, strings.wizard_engine_missing

    def _resolve_engine(self, key: str, ram_gb: float) -> tuple[Enum, str]:
        """
        Keeps the user's engine choice if it fits, otherwise recommends one.

        Parameters
        ----------
        key : str
            The engine preference key in GlobalPrefCategoryList.SYNTH.
        ram_gb : float
            RAM allocated per subject.

        Returns
        -------
        tuple
            The enum member and its review note ("" if it fits).

        """

        entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH][key]
        choice = self.user_prefs.engines.get(key)
        if choice is not None and self._is_option_available(entry, choice, ram_gb):
            return choice, ""
        return self._select_engine(key, ram_gb)

    def _build_plan(self, resources: dict) -> WizardPlan:
        """
        Resolves the wizard choices into the settings to apply.

        Parameters
        ----------
        resources : dict
            PERFORMANCE preferences of the chosen resources, see
            ConfigManager.get_resource_profile_values.

        Returns
        -------
        WizardPlan
            The resolved settings.

        """

        plan = WizardPlan(resources=resources)
        ram_gb = plan.ram_gb
        prefs = self.user_prefs
        plan.cuda = bool(prefs.gpu_capable and prefs.use_gpu_acceleration)

        for key in ENGINE_PREFERENCE_ORDER:
            engine, note = self._resolve_engine(key, ram_gb)
            plan.engines[key] = engine
            if note:
                plan.engine_notes[key] = note

        use_synth = prefs.synth_capable and prefs.use_synth_freesurfer
        reconall_entry = GLOBAL_PREFERENCES[GlobalPrefCategoryList.SYNTH]["reconall"]
        plan.synth_reconall = use_synth and all(
            ram_gb >= threshold
            for key, threshold in reconall_entry.pref_requirement.get(
                GlobalPrefCategoryList.PERFORMANCE, []
            )
            if key == "ram_gb"
        )

        fs_entry = WF_PREFERENCES[DataInputList.T13D]["freesurfer_step"]
        if not prefs.freesurfer_capable:
            plan.freesurfer_step = FreesurferStep.DISABLED
        elif (
            prefs.cortical_parcellation_enabled
            and not prefs.hippocampal_segmentation_enabled
            and not prefs.surfaces_enabled
            and not prefs.full_reconall_enabled
            and use_synth
            and self._is_option_available(fs_entry, FreesurferStep.SYNTHSEG, ram_gb)
        ):
            plan.freesurfer_step = FreesurferStep.SYNTHSEG
        elif prefs.full_reconall_enabled:
            plan.freesurfer_step = FreesurferStep.RECONALL
        elif (
            prefs.cortical_parcellation_enabled
            or prefs.surfaces_enabled
            or prefs.hippocampal_segmentation_enabled
        ):
            # Hippocampal subfields need the FreeSurfer surfaces
            plan.freesurfer_step = FreesurferStep.AUTORECON_PIAL

        plan.hippo_amyg_labels = bool(
            prefs.freesurfer_capable
            and prefs.matlab_capable
            and prefs.hippocampal_segmentation_enabled
        )

        return plan

    def _apply_settings_config(self) -> None:
        """
        Applies the wizard choices to the global configuration and saves it.

        The resource profile is applied first; the remaining settings are
        resolved by `_build_plan` against the RAM per subject it set. Every
        setting the wizard owns is written explicitly, so rerunning the wizard
        also turns off what a previous run enabled.

        Returns
        -------
        None.

        """

        self.global_config.apply_resource_profile(
            self.user_prefs.performance_profile, self.user_prefs.parallel_subjects
        )
        perf = GlobalPrefCategoryList.PERFORMANCE
        plan = self._build_plan(
            {
                "ram_gb": self.global_config.getfloat_safe(perf, "ram_gb"),
                "max_subj_cpu": self.global_config.getint_safe(perf, "max_subj_cpu"),
                "max_subj": self.global_config.getint_safe(perf, "max_subj"),
            }
        )

        self.global_config[perf]["cuda"] = str(plan.cuda)
        for key, engine in plan.engines.items():
            self.global_config[GlobalPrefCategoryList.SYNTH][key] = engine.name
        self.global_config[GlobalPrefCategoryList.SYNTH]["reconall"] = str(
            plan.synth_reconall
        )
        self.global_config[DataInputList.T13D][
            "freesurfer_step"
        ] = plan.freesurfer_step.name
        self.global_config[DataInputList.T13D]["hippo_amyg_labels"] = str(
            plan.hippo_amyg_labels
        )

        self.global_config.save()
