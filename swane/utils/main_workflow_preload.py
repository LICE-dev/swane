"""Background preload of the Nipype main workflow module.

Importing swane.nipype_pipeline.MainWorkflow pulls in nipype, dipy, scipy,
sklearn and nilearn and takes seconds. GUI-thread code paths import it lazily
(e.g. Subject.result_dir while a SubjectTab is built), which would stall the Qt
event loop. Importing it once in a background thread right after the main
window is shown moves that cost off the GUI thread: later imports find the
module in sys.modules, or wait on its import lock while the preload finishes.
The preload thread never touches Qt objects.
"""

import importlib
import logging
import sys
import threading
from typing import Optional

MAIN_WORKFLOW_MODULE = "swane.nipype_pipeline.MainWorkflow"

_preload_thread: Optional[threading.Thread] = None
_preload_lock = threading.Lock()


def _preload(module_name: str):
    try:
        importlib.import_module(module_name)
    except Exception:
        # Not fatal: callers keep their lazy import and will retry on first use
        logging.getLogger(__name__).warning(
            "Background preload of %s failed, it will be imported on first use",
            module_name,
            exc_info=True,
        )


def start_main_workflow_preload(
    module_name: str = MAIN_WORKFLOW_MODULE,
) -> Optional[threading.Thread]:
    """
    Starts importing module_name in a daemon thread, at most once at a time.

    Parameters
    ----------
    module_name: str
        The module to import. Default is MAIN_WORKFLOW_MODULE.

    Returns
    -------
    The preload thread, or None if the module is already imported.
    """
    global _preload_thread
    with _preload_lock:
        if module_name in sys.modules:
            return None
        if _preload_thread is None or not _preload_thread.is_alive():
            _preload_thread = threading.Thread(
                target=_preload,
                args=(module_name,),
                name="swane-main-workflow-preload",
                daemon=True,
            )
            _preload_thread.start()
        return _preload_thread
