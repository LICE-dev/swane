"""Runtime generator for a *phantom* SWANe subject.

The package builds, from scratch and at run time, a complete synthetic DICOM
dataset covering every :class:`swane.utils.DataInputList.DataInputList` entry,
so the workflow tests never need real (or even anonymised) patient data.

Nothing is committed to the repository: the anatomy is derived at run time from
``$FREESURFER_HOME/subjects/fsaverage`` (shipped with every FreeSurfer install)
and the result is cached on disk between runs.

Pipeline, in three independent stages:

``tissue``
    fsaverage segmentations -> a tissue class map in real anatomical scale.
``sequences``
    tissue class map -> per-modality intensity volumes (T1w, FLAIR, CT, DWI...).
``dicom_writer``
    intensity volumes -> DICOM series that ``dcm2niix`` converts correctly.
"""
