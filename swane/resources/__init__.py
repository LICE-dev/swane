import os

okIcon_file = os.path.join(os.path.dirname(__file__), "icons/ok.svg")
errorIcon_file = os.path.join(os.path.dirname(__file__), "icons/error.svg")
warnIcon_file = os.path.join(os.path.dirname(__file__), "icons/warn.svg")
loadingMovie_file = os.path.join(os.path.dirname(__file__), "icons/load.svg")
voidsvg_file = os.path.join(os.path.dirname(__file__), "icons/void.svg")
appIcon_file = os.path.join(os.path.dirname(__file__), "icons/swane.png")
appIcns_file = os.path.join(os.path.dirname(__file__), "icons/swane.icns")


binary_cerebellum = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "atlas/FLAT1/binary_cerebellum.nii.gz")
)
cortex_mas = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "atlas/FLAT1/brain_cortex_mas_OK.nii.gz")
)
mean_extension = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "atlas/FLAT1/mean_extension.nii.gz")
)
mean_flair = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "atlas/FLAT1/mean_flair.nii.gz")
)
std_final_extension = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "atlas/FLAT1/std_final_extension.nii.gz")
)
std_final_flair = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "atlas/FLAT1/std_final_flair.nii.gz")
)
