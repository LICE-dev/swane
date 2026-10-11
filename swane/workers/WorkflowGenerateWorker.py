from PySide6.QtCore import QRunnable, Signal, QObject
from swane.utils.Subject import SubjectRet, Subject


class WorkerSignals(QObject):
    finished = Signal(SubjectRet)
    progress_msg = Signal(str)


class WorkflowGenerateWorker(QRunnable):
    """
    Worker thread for generating a SWANe nipype workflow.
    Prevents UI freezing when parsing the graph or downloading templates.
    """

    def __init__(self, subject: Subject, generate_graphs: bool = True):
        super().__init__()
        self.subject = subject
        self.generate_graphs = generate_graphs
        self.signal = WorkerSignals()

    def run(self):
        from swane.resources import strings

        # Each preload is independent: one failure must not skip the others.
        for preload in (
            self._preload_templates,
            self._preload_models,
            self._preload_dipy_atlas,
        ):
            try:
                preload(strings)
            except Exception as e:
                from subprocess import CalledProcessError

                if isinstance(e, CalledProcessError):
                    print(
                        f"Warning: antspynet weights pre-fetch failed (exit code {e.returncode}):"
                    )
                    print((e.stderr or "")[-2000:])
                else:
                    print(f"Warning: dependency preload failed: {e}")
                # Continue even if preload fails, generate_workflow will handle errors

        self.signal.progress_msg.emit(strings.subj_tab_wf_gen_start)
        ret = self.subject.generate_workflow(generate_graphs=self.generate_graphs)
        self.signal.finished.emit(ret)

    def _preload_templates(self, strings):
        """
        Pre-downloads all templates used by SWANe.
        """
        from swane.utils.templates import get_swane_template
        from pathlib import Path

        templates_to_fetch = [
            ("MNI152NLin2009cSym", 1, "brain"),
            ("MNI152NLin6Asym", 1, "brain"),
            ("MNI152NLin6Asym", 2, "brain"),
        ]

        # Fast check if all are already available
        _SWANE_TEMPLATE_CACHE = Path.home() / ".cache" / "swane" / "templates"
        needs_download = False
        for name, res, desc in templates_to_fetch:
            las_filename = f"{name}_res-{res}_desc-{desc}_T1w_LAS.nii.gz"
            las_path = _SWANE_TEMPLATE_CACHE / las_filename
            if not las_path.exists():
                needs_download = True
                break

        if needs_download:
            self.signal.progress_msg.emit(strings.subj_tab_wf_gen_templates)
            for name, res, desc in templates_to_fetch:
                get_swane_template(
                    name=name, resolution=res, desc=desc, enforce_las=True
                )

    def _preload_models(self, strings):
        """
        Pre-downloads all antspynet models used by SWANe.
        """
        from swane.config.config_enums import GlobalPrefCategoryList, DeskullEngine
        from swane.nipype_pipeline.interfaces.utils import resolve_deskull_engine

        synth_config = self.subject.global_config[GlobalPrefCategoryList.SYNTH]
        if resolve_deskull_engine(synth_config) != DeskullEngine.ANTSPYNET:
            return

        from swane.utils.antspynet_weights import (
            WEIGHTS_BY_MODALITY,
            preload_weights,
            weights_are_fetched,
        )

        all_weights = list(set(WEIGHTS_BY_MODALITY.values()))
        if not weights_are_fetched(all_weights):
            self.signal.progress_msg.emit(strings.subj_tab_wf_gen_models)
            preload_weights(all_weights)

    def _preload_dipy_atlas(self, strings):
        """
        Pre-downloads the HCP842 bundle atlas used by the dipy tractography
        engine, only when this subject's workflow will run the dipy
        tractography (DTI loaded, tractography enabled, dipy engine selected).
        """
        from swane.config.config_enums import (
            GlobalPrefCategoryList,
            TractographyEngine,
        )
        from swane.utils.DataInputList import DataInputList as DIL

        if (
            self.subject.global_config.getenum_safe(
                GlobalPrefCategoryList.SYNTH, "tractography_engine"
            )
            != TractographyEngine.DIPY_RECOBUNDLES
            or not self.subject.input_state_list[DIL.DTI].loaded
            or not self.subject.config.getboolean_safe(DIL.DTI, "tractography")
        ):
            return

        from swane.nipype_pipeline.interfaces.dipy.DipyAtlasSLR import (
            DEFAULT_ATLAS_DIR,
            atlas_wholebrain_path,
            ensure_atlas,
        )

        # Fast check, without importing dipy's fetcher
        if atlas_wholebrain_path(DEFAULT_ATLAS_DIR).exists():
            return

        self.signal.progress_msg.emit(strings.subj_tab_wf_gen_dipy_atlas)
        ensure_atlas(DEFAULT_ATLAS_DIR)
