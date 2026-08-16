#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SWANe Slicer startup bootstrap.

Imported at Slicer startup by the small stub SWANe manages inside the user's
``~/.slicerrc.py`` (see SlicerCheckWorker). Keeping the real logic here, in a
file that ships with SWANe, means the stub in slicerrc never has to change:
updating SWANe updates this file, and the next Slicer session picks up the new
behaviour automatically.

Currently this activates the automatic MELODIC resting-state timecourse
viewer, so the timecourse plot of a component appears as soon as the user
looks at it -- including when a scene is opened manually, outside SWANe.
"""

try:
    from slicer_script_result import install_melodic_timecourse_viewer

    install_melodic_timecourse_viewer()
except Exception as swane_bootstrap_error:  # pragma: no cover - defensive
    print("SWANE: could not install MELODIC timecourse viewer:", swane_bootstrap_error)
