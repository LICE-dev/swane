from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QWidget,
    QPushButton,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QCheckBox
)

from swane import strings
from swane.config.ConfigManager import ConfigManager
from swane.utils.ResourceManager import ResourceManager
from swane.utils.DependencyManager import DependencyManager


class PerformanceProfile(str, Enum):
    """
    Enumeration of performance profiles selectable in the configuration wizard.

    Each value represents a user-facing profile that SWANe can use to balance
    performance and resource usage.

    Notes
    -----
    The enum values are localized strings from `swane.strings`.
    
    """
    
    MAX_PERF = strings.performance_profile_max
    BALANCED = strings.performance_profile_balanced
    LOW_RESOURCE = strings.performance_profile_min


@dataclass
class UserPreferences:
    """
    Container for user selections collected by the configuration wizard.

    This dataclass stores the choices made during the wizard navigation and is
    used to generate the final review summary and (later) apply settings to SWANe.

    Attributes
    ----------
    performance_profile : PerformanceProfile
        Selected performance profile. Defaults to `PerformanceProfile.BALANCED`.
    gpu_capable : bool
        Whether the current system appears to support GPU/CUDA acceleration.
    use_gpu_acceleration : bool or None
        GPU acceleration preference.
        - True: user wants GPU acceleration
        - False: user explicitly disabled GPU acceleration
        - None: GPU acceleration is not available on this system
    use_advanced_models : bool
        Whether advanced models should be used when supported.
        
    """
    
    # Wizard selections
    performance_profile: PerformanceProfile = PerformanceProfile.BALANCED

    # Hardware Acceleration (only meaningful if gpu_capable=True)
    gpu_capable: bool = False
    use_gpu_acceleration: Optional[bool] = None  # True/False if capable, None if not available

    # Advanced models selection
    use_advanced_models: bool = False
    
    # Freesurfer outputs selection (only meaningful if freesurfer_capable=True)
    freesurfer_capable: bool = False
    matlab_capable: bool = False
    cortilcal_parcellation_enabled: bool = False
    surfaces_enabled: bool = False
    hippocampal_segmentation_enabled: bool = False
    full_reconall_enabled: bool = False


class PreferenceWizardWindow(QDialog):
    """
    Wizard dialog for selecting SWANe configuration preferences.

    The wizard guides the user through a multi-step configuration flow:
    1) Welcome
    2) Performance profile selection
    3) Hardware acceleration selection (only if GPU/CUDA capable)
    4) Advanced models selection
    5) Review summary
    6) Configuration applied

    Parameters
    ----------
    my_config : object
        SWANe configuration handler instance used by the application.
        (Currently not modified by this wizard, but stored for future use.)
    dependency_manager : object
        SWANe dependency manager instance used to check optional capabilities
        (e.g., GPU/CUDA availability).
    parent : QWidget, optional
        Parent widget.

    Attributes
    ----------
    my_config : object
        Stored configuration object passed to the constructor.
    dependency_manager : object
        Stored dependency manager passed to the constructor.
    user_prefs : UserPreferences
        The in-memory container of user choices collected by the wizard.
        
    """

    def __init__(self, global_config: ConfigManager, dependency_manager: DependencyManager, parent=None):
        """
        Initializes the configuration wizard dialog and builds the page flow.

        The constructor:
        - sets up the stacked page widget and navigation buttons
        - detects GPU capability to decide whether to show the acceleration page
        - builds wizard pages and initializes the UI state

        Parameters
        ----------
        global_config : ConfigManager
            SWANe configuration handler instance.
        dependency_manager : DependencyManager
            SWANe dependency manager instance.
        parent : QWidget, optional
            Parent widget.

        Returns
        -------
        None.
        
        """
    
        super(PreferenceWizardWindow, self).__init__(parent)

        self.global_config = global_config
        self.dependency_manager = dependency_manager
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
        if self.user_prefs.gpu_capable:
            self.user_prefs.use_gpu_acceleration = True  # default choice if available
        else:
            self.user_prefs.use_gpu_acceleration = None
            
        self.user_prefs.freesurfer_capable = self.dependency_manager.is_freesurfer()
        self.user_prefs.matlab_capable = self.dependency_manager.is_freesurfer_matlab()

        # Build wizard flow
        self._build_pages()
        self._sync_ui()

    # --------------------------
    # Pages builder
    # --------------------------

    def _build_pages(self) -> None:
        """
        Builds and registers all wizard pages according to the current environment.

        The Hardware Acceleration page is added only when the system is detected as
        GPU/CUDA capable.
        The Freesurfer Outputs page is added only when FreeSurfer is detected.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
    
        self._add_page(self._page_welcome())
        self._add_page(self._page_performance_profile())

        if self.user_prefs.gpu_capable:
            self._add_page(self._page_hardware_acceleration())

        self._add_page(self._page_advanced_models())
        
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

    def _make_title(self, title: str, body: str) -> QWidget:
        """
        Creates a standardized title/header widget for wizard pages.

        The returned widget contains:
        - a title label with larger/bold font
        - a word-wrapped body/description label
        - a horizontal separator line

        Parameters
        ----------
        title : str
            Page title text.
        body : str
            Page description text.

        Returns
        -------
        QWidget
            A widget containing the formatted page header.
            
        """
    
        w = QWidget()
        lay = QVBoxLayout()
        t = QLabel(title)
        t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        t.setStyleSheet("font-size: 18px; font-weight: 600;")
        b = QLabel(body)
        b.setWordWrap(True)
        b.setTextInteractionFlags(Qt.TextSelectableByMouse)

        lay.addWidget(t)
        lay.addWidget(b)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)

        w.setLayout(lay)
        return w

    # --------------------------
    # Page 1: Welcome
    # --------------------------

    def _page_welcome(self) -> QWidget:
        """
        Creates the Welcome/Intro wizard page.

        This page introduces the configuration wizard and changes the "Next" button
        label to the localized "Start" label.

        Parameters
        ----------
        None.

        Returns
        -------
        QWidget
            The constructed Welcome page widget.
            
        """
    
        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(self._make_title(strings.wizard_welcome_title, strings.wizard_welcome_text))

        lay.addStretch(1)
        page.setLayout(lay)

        # Custom Attribute to rename Next button
        page._wizard_next_label = strings.wizard_start_button  # type: ignore[attr-defined]
        return page

    # --------------------------
    # Page 2: Performance Profile
    # --------------------------

    def _page_performance_profile(self) -> QWidget:
        """
        Creates the Performance Profile selection wizard page.

        The page allows choosing between:
        - maximum performance
        - balanced
        - low resource usage

        Parameters
        ----------
        None.

        Returns
        -------
        QWidget
            The constructed Performance Profile page widget.
            
        """
    
        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(self._make_title(strings.wizard_performance_title, strings.wizard_performance_text))

        self._perf_group = QButtonGroup(self)

        rb_max = QRadioButton(strings.performance_profile_max + "\n" + strings.performance_profile_max_tooltip)
        rb_bal = QRadioButton(strings.performance_profile_balanced + "\n" + strings.performance_profile_balanced_tooltip)
        rb_low = QRadioButton(strings.performance_profile_min + "\n" + strings.performance_profile_min_tooltip)

        self._perf_group.addButton(rb_max, 0)
        self._perf_group.addButton(rb_bal, 1)
        self._perf_group.addButton(rb_low, 2)

        lay.addWidget(rb_max)
        lay.addWidget(rb_bal)
        lay.addWidget(rb_low)
        lay.addStretch(1)
        page.setLayout(lay)

        # default selection
        rb_bal.setChecked(True)

        return page

    # --------------------------
    # Page 3: Hardware Acceleration (optional)
    # --------------------------

    def _page_hardware_acceleration(self) -> QWidget:
        """
        Creates the Hardware Acceleration selection wizard page.

        This page is only added to the wizard flow when the system is detected as
        GPU/CUDA capable.

        Parameters
        ----------
        None.

        Returns
        -------
        QWidget
            The constructed Hardware Acceleration page widget.
            
        """
    
        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(self._make_title(strings.wizard_hardware_accelleration_title, strings.wizard_hardware_accelleration_text))

        self._gpu_group = QButtonGroup(self)

        rb_gpu = QRadioButton(strings.gpu_acceleration_enabled + "\n" + strings.gpu_acceleration_enabled_tooltip)
        rb_cpu = QRadioButton(strings.gpu_acceleration_disabled + "\n" + strings.gpu_acceleration_disabled_tooltip)

        self._gpu_group.addButton(rb_gpu, 1)
        self._gpu_group.addButton(rb_cpu, 0)

        lay.addWidget(rb_gpu)
        lay.addWidget(rb_cpu)
        lay.addStretch(1)
        page.setLayout(lay)

        # default: GPU on if available
        rb_gpu.setChecked(True)

        return page

    # --------------------------
    # Page 4: Advanced Models
    # --------------------------

    def _page_advanced_models(self) -> QWidget:
        """
        Creates the Advanced Models selection wizard page.

        The page allows choosing whether SWANe should enable advanced models when supported
        or use only standard methods.

        Parameters
        ----------
        None.

        Returns
        -------
        QWidget
            The constructed Advanced Models page widget.
            
        """
    
        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(self._make_title(strings.wizard_advanced_models_title, strings.wizard_advanced_models_text))

        self._adv_group = QButtonGroup(self)

        rb_adv = QRadioButton(strings.advanced_models_enabled + "\n" + strings.advanced_models_enabled_tooltip)
        rb_std = QRadioButton(strings.advanced_models_disabled + "\n" + strings.advanced_models_disabled_tooltip)

        self._adv_group.addButton(rb_adv, 1)
        self._adv_group.addButton(rb_std, 0)

        lay.addWidget(rb_adv)
        lay.addWidget(rb_std)
        lay.addStretch(1)
        page.setLayout(lay)

        rb_adv.setChecked(True)
        return page
    
    # --------------------------
    # Page 5: FreeSurfer Outputs
    # --------------------------

    def _page_freesurfer_outputs(self) -> QWidget:
        """
        Creates the FreeSurfer Outputs selection wizard page.

        The page allows choosing which FreeSurfer outputs SWANe should enable.
        Options are independent and mapped to self.user_prefs:
        - cortilcal_parcellation_enabled
        - surfaces_enabled
        - hippocampal_segmentation_enabled
        - full_reconall_enabled

        Parameters
        ----------
        None

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
            )
        )

        self._cb_freesurfer_cortical_parcellation = QCheckBox(
            f"{strings.freesurfer_outputs_cortical_parcellation}\n"
            f"{strings.freesurfer_outputs_cortical_parcellation_tooltip}"
        )
        self._cb_freesurfer_cortical_parcellation.toggled.connect(
            lambda checked: setattr(self.user_prefs, "cortilcal_parcellation_enabled", bool(checked))
        )
        lay.addWidget(self._cb_freesurfer_cortical_parcellation)
        
        self._cb_freesurfer_surfaces = QCheckBox(
            f"{strings.freesurfer_outputs_surfaces}\n"
            f"{strings.freesurfer_outputs_surfaces_tooltip}"
        )
        self._cb_freesurfer_surfaces.toggled.connect(
            lambda checked: setattr(self.user_prefs, "surfaces_enabled", bool(checked))
        )
        lay.addWidget(self._cb_freesurfer_surfaces)
        
        if not self.user_prefs.matlab_capable:
            self._cb_freesurfer_hippocampal_segmentation = QCheckBox(
                f"{strings.freesurfer_outputs_hippocampal_segmentation}\n"
                f"{strings.freesurfer_outputs_hippocampal_segmentation_tooltip}"
            )
            self._cb_freesurfer_hippocampal_segmentation.toggled.connect(
                lambda checked: setattr(self.user_prefs, "hippocampal_segmentation_enabled", bool(checked))
            )
            lay.addWidget(self._cb_freesurfer_hippocampal_segmentation)
            
        self._cb_freesurfer_full_reconall = QCheckBox(
            f"{strings.freesurfer_full_reconall}\n"
            f"{strings.freesurfer_full_reconall_tooltip}"
        )
        self._cb_freesurfer_full_reconall.toggled.connect(
            lambda checked: setattr(self.user_prefs, "full_reconall_enabled", bool(checked))
        )
        lay.addWidget(self._cb_freesurfer_full_reconall)

        lay.addStretch(1)
        page.setLayout(lay)

        return page

    # --------------------------
    # Page 5: Review
    # --------------------------

    def _page_review(self) -> QWidget:
        """
        Creates the Review wizard page.

        This page displays a summary of the current selections and informs the user that
        some options may be automatically adjusted for stability and compatibility.

        Parameters
        ----------
        None.

        Returns
        -------
        QWidget
            The constructed Review page widget.
            
        """
    
        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(self._make_title(strings.wizard_review_title, strings.wizard_review_text))

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
        
        return page

    # --------------------------
    # Page 6: Applied
    # --------------------------

    def _page_applied(self) -> QWidget:
        """
        Creates the final "Configuration Applied" wizard page.

        The page confirms the configuration has been applied (UI-only for now) and provides
        closing messaging.

        Parameters
        ----------
        None.

        Returns
        -------
        QWidget
            The constructed Applied page widget.
            
        """
    
        page = QWidget()
        lay = QVBoxLayout()
        lay.addWidget(self._make_title(strings.wizard_applied_title, strings.wizard_applied_text))
        lay.addStretch(1)
        page.setLayout(lay)
        
        return page

    # --------------------------
    # Wizard flow + persistence
    # --------------------------

    def _apply_current_page(self) -> None:
        """
        Stores the current page selections into the `user_prefs` object.

        This method reads the checked states from the available radio-button groups:
        - performance profile group
        - GPU acceleration group (only if available)
        - advanced models group

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
        
        w = self._stack.currentWidget()

        # Performance page
        if hasattr(self, "_perf_group") and w is self._pages[self._index_of_page_widget(w)]:
            # Not robust by identity of widgets; we instead check existence of group & whether it has a checkedButton
            pass

        # Save by checking which groups exist + checked
        if hasattr(self, "_perf_group") and self._perf_group.checkedButton() is not None:
            bid = self._perf_group.checkedId()
            if bid == 0:
                self.user_prefs.performance_profile = PerformanceProfile.MAX_PERF
            elif bid == 1:
                self.user_prefs.performance_profile = PerformanceProfile.BALANCED
            elif bid == 2:
                self.user_prefs.performance_profile = PerformanceProfile.LOW_RESOURCE

        if self.user_prefs.gpu_capable and hasattr(self, "_gpu_group") and self._gpu_group.checkedButton() is not None:
            self.user_prefs.use_gpu_acceleration = bool(self._gpu_group.checkedId())

        if hasattr(self, "_adv_group") and self._adv_group.checkedButton() is not None:
            self.user_prefs.use_advanced_models = bool(self._adv_group.checkedId())

    def _index_of_page_widget(self, w: QWidget) -> int:
        """
        Returns the index of a page widget in the internal page list.

        Parameters
        ----------
        w : QWidget
            Page widget to locate.

        Returns
        -------
        int
            Index of the widget in the wizard page list, or -1 if not found.
            
        """
    
        for i, p in enumerate(self._pages):
            if p is w:
                return i
        return -1

    def _update_review_page(self) -> None:
        """
        Updates the Review page summary text based on the current `user_prefs`.

        The method generates user-facing status strings for:
        - selected performance profile
        - GPU acceleration state (enabled/disabled/not available)
        - advanced models state
        - FreeSurfer outputs state

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
    
        # Profile
        profile = self.user_prefs.performance_profile.value

        # GPU status
        if not self.user_prefs.gpu_capable:
            gpu_txt = strings.gpu_not_available
        else:
            gpu_txt = strings.gpu_enabled if self.user_prefs.use_gpu_acceleration else strings.gpu_disabled

        # Advanced models status (placeholder logic for “partially enabled / not available”)
        # Per ora: o enabled o disabled. Quando avremo info su RAM/compatibilità, possiamo aggiungere "partially".
        if self.user_prefs.use_advanced_models:
            adv_txt = strings.advanced_models_enabled
        else:
            adv_txt = strings.advanced_models_disabled

        self._review_label.setText(
            f"{strings.wizard_selected_profile.format(profile=profile)}<br /><br />"
            f"{strings.wizard_gpu_accelleration.format(gpu_status=gpu_txt)}<br /><br />"
            f"{strings.wizard_advanced_models.format(adv_status=adv_txt)}<br /><br />"
        )
        
        freesurfer_info_text = ""
        if not self.user_prefs.freesurfer_capable:
            freesurfer_info_text = strings.wizard_freesurfer_outputs.format(fs_outputs="Not Detected")
        else:
            freesurfer_outputs_enabled = []
            if self.user_prefs.cortilcal_parcellation_enabled:
                freesurfer_outputs_enabled.append(strings.freesurfer_outputs_cortical_parcellation)
            if self.user_prefs.surfaces_enabled:
                freesurfer_outputs_enabled.append(strings.freesurfer_outputs_surfaces)
            if self.user_prefs.hippocampal_segmentation_enabled:
                freesurfer_outputs_enabled.append(strings.freesurfer_outputs_hippocampal_segmentation)
            if self.user_prefs.full_reconall_enabled:
                freesurfer_outputs_enabled.append(strings.freesurfer_full_reconall)
        
            if len(freesurfer_outputs_enabled) == 0:
                freesurfer_info_text = strings.wizard_freesurfer_outputs.format(fs_outputs="Disabled")
            else:
                freesurfer_info_text = strings.wizard_freesurfer_outputs.format(fs_outputs=", ".join(freesurfer_outputs_enabled))
                
        self._review_label.setText(
            self._review_label.text() + f"{freesurfer_info_text}"
        )

    # --------------------------
    # Navigation
    # --------------------------

    def _go_back(self) -> None:
        """
        Navigates to the previous wizard page.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
    
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._sync_ui()

    def _go_next(self) -> None:
        """
        Navigates to the next wizard page.

        Before advancing, the method stores the current page selections into `user_prefs`.
        When entering the Review page, the summary text is refreshed.

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
    
        self._apply_current_page()

        idx = self._stack.currentIndex()
        if idx < self._stack.count() - 1:
            self._stack.setCurrentIndex(idx + 1)

            # If we just entered Review page, refresh it
            if self._is_review_page():
                self._apply_current_page()
                self._update_review_page()

            self._sync_ui()

    def _finish(self) -> None:
        """
        Handles the Finish/Apply action depending on the current wizard page.

        Behavior:
        - On the Review page: stores current selections, updates the review, and moves to
        the final "Applied" page.
        - On the Applied page: closes the dialog with `accept()`.
        - On any other page: behaves like "Next".

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
    
        # If we are on review page -> apply and move to applied page
        if self._is_review_page():
            self._apply_current_page()
            self._update_review_page()
            
            self._apply_settings_config()
            
            self._stack.setCurrentIndex(self._stack.count() - 1)
            self._sync_ui()
            return

        # If we are on applied page -> accept dialog
        if self._is_applied_page():
            self.accept()
            return

        # Otherwise behave like next
        self._go_next()

    def _is_review_page(self) -> bool:
        """
        Checks whether the currently displayed page is the Review page.

        Parameters
        ----------
        None.

        Returns
        -------
        bool
            True if the current page is the Review page, False otherwise.
            
        """
    
        w = self._stack.currentWidget()
        return hasattr(self, "_review_label") and (w is self._pages[-2])  # review is penultimate

    def _is_applied_page(self) -> bool:
        """
        Checks whether the currently displayed page is the final Applied page.

        Parameters
        ----------
        None.

        Returns
        -------
        bool
            True if the current page is the Applied page, False otherwise.
            
        """
    
        w = self._stack.currentWidget()
        return w is self._pages[-1]

    def _sync_ui(self) -> None:
        """
        Synchronizes navigation button state and labels with the current wizard page.

        This method:
        - enables/disables Back/Next/Finish as appropriate
        - renames the Next button on the Welcome page to "Get Started"
        - changes Finish button text to "Apply" on the Review page
        - disables navigation and keeps only Finish on the final Applied page

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
    
        idx = self._stack.currentIndex()
        last = self._stack.count() - 1

        self._back_btn.setEnabled(idx > 0)

        # Welcome page: rename Next to "Get Started"
        w = self._stack.currentWidget()
        next_label = getattr(w, "_wizard_next_label", "Next")
        self._next_btn.setText(next_label)

        # On applied page: only Finish enabled
        if self._is_applied_page():
            self._next_btn.setEnabled(False)
            self._finish_btn.setEnabled(True)
            self._finish_btn.setText(strings.wizard_finish_button)
            self._back_btn.setEnabled(False)
            return

        # On review page: Finish means "Apply"
        if self._is_review_page():
            self._next_btn.setEnabled(False)
            self._finish_btn.setEnabled(True)
            self._finish_btn.setText(strings.wizard_apply_button)
            return

        # Normal pages
        self._next_btn.setEnabled(idx < last)
        self._finish_btn.setEnabled(False)
        self._finish_btn.setText(strings.wizard_finish_button)
        
    def _apply_settings_config(self) -> None:
        """
        Applies the wizard selections to the SWANe configuration object.

        This method is responsible for mapping the in-memory wizard choices stored in
        `self.user_prefs` to the corresponding keys inside `self.my_config`, and for
        persisting those changes (e.g., by calling `self.my_config.save()`).

        Notes
        -----
        This method is intentionally left unimplemented for now.
        The exact mapping depends on the SWANe preference categories/keys that should be
        updated (e.g., GLOBAL_PREFERENCES / WF_PREFERENCES).

        Parameters
        ----------
        None.

        Returns
        -------
        None.
        
        """
        # TODO DA FARE
        return