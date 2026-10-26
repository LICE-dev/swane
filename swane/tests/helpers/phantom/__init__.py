"""Runtime generator for a *phantom* SWANe subject.

The package builds, from scratch and at run time, a complete synthetic DICOM
dataset covering every :class:`swane.utils.DataInputList.DataInputList` entry,
so the workflow tests never need real (or even anonymised) subject data.

Nothing is committed to the repository: the anatomy is derived at run time
from the CerebrA atlas and the ICBM 2009c Nonlinear Symmetric tissue maps
(md5-pinned TemplateFlow files, downloaded once), and the result is cached on
disk between runs.

Pipeline, in three independent stages:

``tissue``
    CerebrA labels + GM/WM/CSF probseg -> a tissue class map in real anatomical scale.
``sequences``
    tissue class map -> per-modality intensity volumes (T1w, FLAIR, CT, DWI...).
``dicom_writer``
    intensity volumes -> DICOM series that ``dcm2niix`` converts correctly.
"""
