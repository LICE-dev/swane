import os

okIcon_file=os.path.join(os.path.dirname(__file__), "icons/ok.svg")
errorIcon_file=os.path.join(os.path.dirname(__file__), "icons/error.svg")
warnIcon_file=os.path.join(os.path.dirname(__file__), "icons/warn.svg")
loadingMovie_file = os.path.join(os.path.dirname(__file__), "icons/load.svg")
voidsvg_file = os.path.join(os.path.dirname(__file__), "icons/void.svg")
appIcon_file = os.path.join(os.path.dirname(__file__), "icons/swane.png")
appIcns_file = os.path.join(os.path.dirname(__file__), "icons/swane.icns")

sym_template = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/mni_icbm152_t1_tal_nlin_sym_09c_brain.nii.gz"))

binary_cerebellum = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/doMAP_template/binary_cerebellum.nii.gz"))
cortex_mas = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/doMAP_template/brain_cortex_mas_OK.nii.gz"))
mean_extension = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/doMAP_template/mean_extension.nii.gz"))
mean_flair = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/doMAP_template/mean_flair.nii.gz"))
std_final_extension = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/doMAP_template/std_final_extension.nii.gz"))
std_final_flair = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources/doMAP_template/std_final_flair.nii.gz"))
