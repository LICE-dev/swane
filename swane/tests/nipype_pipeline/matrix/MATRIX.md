# SWANe workflow settings matrix

Overview of 77 construction scenarios across 14 workflow families. Each row is one setting combination; follow the *snapshot* link for the full graph (nodes, commands, flags, wiring).

> Generated from the golden snapshots by `python swane/tests/nipype_pipeline/matrix/generate_report.py` — do not edit by hand. Regenerate after refreshing the snapshots (`SWANE_SNAPSHOT_UPDATE=1 pytest .../matrix`).

[dti_preproc](#dti-preproc) · [flat1](#flat1) · [fmri_preproc](#fmri-preproc) · [fmri_resting_state](#fmri-resting-state) · [fmri_task](#fmri-task) · [freesurfer](#freesurfer) · [func_map](#func-map) · [linear_reg](#linear-reg) · [nonlinear_reg](#nonlinear-reg) · [ref](#ref) · [seeg_ct](#seeg-ct) · [tractography](#tractography) · [venous_ct](#venous-ct) · [venous_mr](#venous-mr)

## dti_preproc

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [new_eddy_cpu_hardcap](snapshots/dti_preproc/new_eddy_cpu_hardcap.txt) | cuda=false; deskull_engine=ANTSPYNET; max_cpu=4; multicore_node_limit=HARD_CAP; old_eddy_correct=false; synth_morph=False; tractography=false | 12 / 21 | `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False` |
| [new_eddy_cpu_softcap](snapshots/dti_preproc/new_eddy_cpu_softcap.txt) | cuda=false; deskull_engine=ANTSPYNET; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; tractography=false | 12 / 21 | `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False` |
| [new_eddy_cuda](snapshots/dti_preproc/new_eddy_cuda.txt) | cuda=true; deskull_engine=ANTSPYNET; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; tractography=false | 12 / 21 | `convert_xfm`, `dcm2niix`, `dtifit`, `eddy`, `flirt` | `use_cuda=True` |
| [new_eddy_tractography](snapshots/dti_preproc/new_eddy_tractography.txt) | cuda=false; deskull_engine=ANTSPYNET; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; tractography=true | 13 / 25 | `bedpostx`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False`, `use_gpu=False` |
| [old_eddy_correct](snapshots/dti_preproc/old_eddy_correct.txt) | cuda=false; deskull_engine=ANTSPYNET; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=true; synth_morph=False; tractography=false | 11 / 17 | `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_correct`, `flirt` | — |
| [test_run](snapshots/dti_preproc/test_run.txt) | cuda=false; deskull_engine=ANTSPYNET; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; test_run=True; tractography=true | 13 / 25 | `bedpostx`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False`, `use_gpu=False` |

## flat1

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [ants_backend](snapshots/flat1/ants_backend.txt) | registration_engine=ANTS; synth_morph=false | 37 / 55 | `fast`, `fslmaths` | — |
| [fsl_backend](snapshots/flat1/fsl_backend.txt) | registration_engine=FSL; synth_morph=false | 30 / 44 | `applywarp`, `fast`, `fslmaths` | — |
| [fsl_backend_test_run](snapshots/flat1/fsl_backend_test_run.txt) | synth_morph=false; test_run=True | 30 / 44 | `applywarp`, `fast`, `fslmaths` | — |
| [synthmorph_backend](snapshots/flat1/synthmorph_backend.txt) | registration_engine=SYNTH; synth_morph=true | 30 / 44 | `fast`, `fslmaths`, `mri_synthmorph` | — |
| [synthmorph_backend_test_run](snapshots/flat1/synthmorph_backend_test_run.txt) | synth_morph=true; test_run=True | 30 / 44 | `fast`, `fslmaths`, `mri_synthmorph` | — |

## fmri_preproc

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [slicetiming_interleaved](snapshots/fmri_preproc/slicetiming_interleaved.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=INTERLEAVED | 27 / 41 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |
| [slicetiming_unknown](snapshots/fmri_preproc/slicetiming_unknown.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=UNKNOWN | 26 / 39 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `susan` | — |
| [slicetiming_up](snapshots/fmri_preproc/slicetiming_up.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=UP | 27 / 41 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |
| [test_run](snapshots/fmri_preproc/test_run.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=UP; test_run=True | 27 / 41 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |
| [trim_start_end_vols](snapshots/fmri_preproc/trim_start_end_vols.txt) | TR=3.0; del_end_vols=3; del_start_vols=5; hpcutoff=50; n_vols=120; slice_timing=UP | 27 / 41 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |

## fmri_resting_state

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [aroma_on](snapshots/fmri_resting_state/aroma_on.txt) | aroma=true; melodic_dim=0; melodic_thr=0.5 | 44 / 75 | `applywarp`, `convertwarp`, `dcm2niix`, `flirt`, `fnirt`, `fsl_regfilt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |
| [melodic_auto_dim](snapshots/fmri_resting_state/melodic_auto_dim.txt) | aroma=false; melodic_dim=0; melodic_thr=0.5 | 31 / 49 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |
| [melodic_fixed_dim](snapshots/fmri_resting_state/melodic_fixed_dim.txt) | aroma=false; melodic_dim=30; melodic_thr=0.9 | 31 / 49 | `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |
| [test_run](snapshots/fmri_resting_state/test_run.txt) | aroma=true; melodic_dim=0; melodic_thr=0.5; test_run=True | 44 / 75 | `applywarp`, `convertwarp`, `dcm2niix`, `flirt`, `fnirt`, `fsl_regfilt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |

## fmri_task

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [single_contrast_rara](snapshots/fmri_task/single_contrast_rara.txt) | block_design=RARA; rest_duration=30; task_a_name=Task_A; task_b_name=Task_B; task_duration=30 | 42 / 86 | `cluster`, `dcm2niix`, `feat_model`, `film_gls`, `flirt`, `fslmaths`, `mcflirt`, `smoothest`, `susan` | — |
| [test_run](snapshots/fmri_task/test_run.txt) | block_design=RARA; rest_duration=30; task_a_name=Task_A; task_b_name=Task_B; task_duration=30; test_run=True | 42 / 86 | `cluster`, `dcm2niix`, `feat_model`, `film_gls`, `flirt`, `fslmaths`, `mcflirt`, `smoothest`, `susan` | — |
| [two_contrasts_rarb](snapshots/fmri_task/two_contrasts_rarb.txt) | block_design=RARB; rest_duration=30; task_a_name=Task_A; task_b_name=Task_B; task_duration=30 | 50 / 116 | `cluster`, `dcm2niix`, `feat_model`, `film_gls`, `flirt`, `fslmaths`, `mcflirt`, `smoothest`, `susan` | — |

## freesurfer

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [autorecon_pial](snapshots/freesurfer/autorecon_pial.txt) | hippo_amyg_labels=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=AUTORECON_PIAL; synth_reconall=false; synthseg_fast=False | 11 / 16 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [disabled_returns_none](snapshots/freesurfer/disabled_returns_none.txt) | hippo_amyg_labels=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=DISABLED; synth_reconall=false; synthseg_fast=False | None | — | — |
| [reconall](snapshots/freesurfer/reconall.txt) | hippo_amyg_labels=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; synth_reconall=false; synthseg_fast=False | 12 / 18 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [reconall_hippo](snapshots/freesurfer/reconall_hippo.txt) | hippo_amyg_labels=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; synth_reconall=false; synthseg_fast=False | 15 / 25 | `fslmaths`, `mri_vol2vol`, `recon-all`, `segmentHA_T1.sh` | — |
| [reconall_synth_tools](snapshots/freesurfer/reconall_synth_tools.txt) | hippo_amyg_labels=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; synth_reconall=true; synthseg_fast=False | 12 / 18 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [reconall_test_run](snapshots/freesurfer/reconall_test_run.txt) | max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; test_run=True | 12 / 18 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [synthseg](snapshots/freesurfer/synthseg.txt) | hippo_amyg_labels=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=SYNTHSEG; synth_reconall=false; synthseg_fast=False | 8 / 11 | `fslmaths`, `mri_synthseg`, `mri_vol2vol` | — |
| [synthseg_fast](snapshots/freesurfer/synthseg_fast.txt) | hippo_amyg_labels=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; step=SYNTHSEG; synth_reconall=false; synthseg_fast=True | 8 / 11 | `fslmaths`, `mri_synthseg`, `mri_vol2vol` | — |
| [synthseg_limit_cores](snapshots/freesurfer/synthseg_limit_cores.txt) | hippo_amyg_labels=False; limit_synth_cores=true; max_cpu=4; multicore_node_limit=SOFT_CAP; step=SYNTHSEG; synth_reconall=false; synthseg_fast=False | 8 / 11 | `fslmaths`, `mri_synthseg`, `mri_vol2vol` | — |
| [synthseg_test_run](snapshots/freesurfer/synthseg_test_run.txt) | max_cpu=4; multicore_node_limit=SOFT_CAP; step=SYNTHSEG; test_run=True | 8 / 11 | `fslmaths`, `mri_synthseg`, `mri_vol2vol` | — |

## func_map

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [ants_backend](snapshots/func_map/ants_backend.txt) | ai=true; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=DISABLED; registration_engine=ANTS | 16 / 25 | `dcm2niix`, `fslmaths` | — |
| [no_freesurfer_ai](snapshots/func_map/no_freesurfer_ai.txt) | ai=true; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=DISABLED | 14 / 22 | `applywarp`, `dcm2niix`, `flirt`, `fslmaths` | — |
| [no_freesurfer_no_ai](snapshots/func_map/no_freesurfer_no_ai.txt) | ai=false; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=DISABLED | 8 / 11 | `dcm2niix`, `flirt`, `fslmaths` | — |
| [pet_reconall_ai](snapshots/func_map/pet_reconall_ai.txt) | ai=true; config=PET; cost_func=MUTUAL_INFORMATION; freesurfer_step=RECONALL | 21 / 43 | `applywarp`, `dcm2niix`, `flirt`, `fslmaths`, `mri_vol2surf` | — |
| [reconall_ai](snapshots/func_map/reconall_ai.txt) | ai=true; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=RECONALL | 21 / 43 | `applywarp`, `dcm2niix`, `flirt`, `fslmaths`, `mri_vol2surf` | — |
| [reconall_no_ai](snapshots/func_map/reconall_no_ai.txt) | ai=false; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=RECONALL | 13 / 26 | `dcm2niix`, `flirt`, `fslmaths`, `mri_vol2surf` | — |
| [synthseg_no_ai](snapshots/func_map/synthseg_no_ai.txt) | ai=false; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=SYNTHSEG | 9 / 14 | `dcm2niix`, `flirt`, `fslmaths` | — |
| [test_run](snapshots/func_map/test_run.txt) | ai=false; config=ASL; cost_func=NORMALIZED_MUTUAL_INFORMATION; freesurfer_step=DISABLED; test_run=True | 8 / 11 | `dcm2niix`, `flirt`, `fslmaths` | — |

## linear_reg

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [flair2d_non_volumetric](snapshots/linear_reg/flair2d_non_volumetric.txt) | bias_field_correction=False; config=None; deskull_engine=BET; is_partial_coverage=False; is_volumetric=False; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=FSL; synth_morph=false | 11 / 18 | `bet`, `dcm2niix`, `flirt`, `robustfov` | — |
| [flair3d_ants_backend](snapshots/linear_reg/flair3d_ants_backend.txt) | bias_field_correction=True; config=FLAIR3D; deskull_engine=ANTSPYNET; is_partial_coverage=False; is_volumetric=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=ANTS; synth_morph=false | 13 / 26 | `dcm2niix`, `fslmaths`, `robustfov` | — |
| [flair3d_bias](snapshots/linear_reg/flair3d_bias.txt) | bias_field_correction=True; config=FLAIR3D; deskull_engine=BET; is_partial_coverage=False; is_volumetric=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=FSL; synth_morph=false | 13 / 26 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |
| [flair3d_no_bias](snapshots/linear_reg/flair3d_no_bias.txt) | bias_field_correction=False; config=FLAIR3D; deskull_engine=BET; is_partial_coverage=False; is_volumetric=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=FSL; synth_morph=false | 11 / 18 | `bet`, `dcm2niix`, `flirt`, `robustfov` | — |
| [flair3d_synth_backend](snapshots/linear_reg/flair3d_synth_backend.txt) | bias_field_correction=True; config=FLAIR3D; deskull_engine=SYNTHSTRIP; is_partial_coverage=False; is_volumetric=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=SYNTH; synth_morph=true | 13 / 24 | `dcm2niix`, `fslmaths`, `mri_synthmorph`, `mri_synthstrip`, `robustfov` | — |
| [flair3d_synth_backend_limit_cores](snapshots/linear_reg/flair3d_synth_backend_limit_cores.txt) | bias_field_correction=True; config=FLAIR3D; deskull_engine=SYNTHSTRIP; is_partial_coverage=False; is_volumetric=True; limit_synth_cores=true; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=SYNTH; synth_morph=true | 13 / 24 | `dcm2niix`, `fslmaths`, `mri_synthmorph`, `mri_synthstrip`, `robustfov` | — |
| [mdc_bias](snapshots/linear_reg/mdc_bias.txt) | bias_field_correction=True; config=MDC; deskull_engine=BET; is_partial_coverage=False; is_volumetric=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=FSL; synth_morph=false | 13 / 26 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |
| [t2cor_partial_coverage](snapshots/linear_reg/t2cor_partial_coverage.txt) | bias_field_correction=False; config=None; deskull_engine=BET; is_partial_coverage=True; is_volumetric=True; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=FSL; synth_morph=false | 10 / 16 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |
| [test_run](snapshots/linear_reg/test_run.txt) | bias_field_correction=True; config=FLAIR3D; deskull_engine=ANTSPYNET; is_partial_coverage=False; is_volumetric=True; synth_morph=False; test_run=True | 13 / 26 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |

## nonlinear_reg

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [ants_backend](snapshots/nonlinear_reg/ants_backend.txt) | limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=ANTS; synth_morph=false | 6 / 10 | — | — |
| [fsl_backend](snapshots/nonlinear_reg/fsl_backend.txt) | limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=FSL; synth_morph=false | 6 / 10 | `applywarp`, `flirt`, `fnirt`, `invwarp` | — |
| [fsl_backend_test_run](snapshots/nonlinear_reg/fsl_backend_test_run.txt) | max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=false; test_run=True | 6 / 10 | `applywarp`, `flirt`, `fnirt`, `invwarp` | — |
| [synthmorph_backend](snapshots/nonlinear_reg/synthmorph_backend.txt) | limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=SYNTH; synth_morph=true | 4 / 5 | `mri_synthmorph` | — |
| [synthmorph_backend_limit_cores](snapshots/nonlinear_reg/synthmorph_backend_limit_cores.txt) | limit_synth_cores=true; max_cpu=4; multicore_node_limit=SOFT_CAP; registration_engine=SYNTH; synth_morph=true | 4 / 5 | `mri_synthmorph` | — |
| [synthmorph_backend_test_run](snapshots/nonlinear_reg/synthmorph_backend_test_run.txt) | max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=true; test_run=True | 4 / 5 | `mri_synthmorph` | — |

## ref

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [antspynet](snapshots/ref/antspynet.txt) | bet_bias_correction=false; bet_thr=0.3; deskull_engine=ANTSPYNET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP | 8 / 12 | `dcm2niix`, `fslmaths`, `robustfov` | — |
| [bet_bias_thr0](snapshots/ref/bet_bias_thr0.txt) | bet_bias_correction=true; bet_thr=0.0; deskull_engine=BET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |
| [bet_default](snapshots/ref/bet_default.txt) | bet_bias_correction=false; bet_thr=0.3; deskull_engine=BET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |
| [bet_thr_high](snapshots/ref/bet_thr_high.txt) | bet_bias_correction=false; bet_thr=1.0; deskull_engine=BET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |
| [synthstrip](snapshots/ref/synthstrip.txt) | bet_bias_correction=false; bet_thr=0.3; deskull_engine=SYNTHSTRIP; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP | 8 / 12 | `dcm2niix`, `fslmaths`, `mri_synthstrip`, `robustfov` | — |
| [synthstrip_limit_cores](snapshots/ref/synthstrip_limit_cores.txt) | bet_bias_correction=false; bet_thr=0.3; deskull_engine=SYNTHSTRIP; limit_synth_cores=true; max_cpu=4; multicore_node_limit=SOFT_CAP | 8 / 12 | `dcm2niix`, `fslmaths`, `mri_synthstrip`, `robustfov` | — |
| [test_run](snapshots/ref/test_run.txt) | bet_bias_correction=false; bet_thr=0.3; deskull_engine=ANTSPYNET; test_run=True | 8 / 12 | `dcm2niix`, `fslmaths`, `robustfov` | — |

## seeg_ct

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [ants_backend](snapshots/seeg_ct/ants_backend.txt) | registration_engine=ANTS | 13 / 16 | `dcm2niix`, `fslmaths` | — |
| [fsl_backend](snapshots/seeg_ct/fsl_backend.txt) | registration_engine=FSL | 13 / 16 | `dcm2niix`, `flirt`, `fslmaths` | — |

## tractography

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [cst_real_graph](snapshots/tractography/cst_real_graph.txt) | cuda=false; tract=cst; xtract_data=present | 13 / 21 | `applywarp`, `probtrackx2` | `use_gpu=False` |
| [cst_real_graph_ants_backend](snapshots/tractography/cst_real_graph_ants_backend.txt) | cuda=false; registration_engine=ANTS; tract=cst; xtract_data=present | 19 / 33 | `probtrackx2` | `use_gpu=False` |
| [cst_real_graph_test_run](snapshots/tractography/cst_real_graph_test_run.txt) | cuda=false; test_run=True; tract=cst; xtract_data=present | 13 / 21 | `applywarp`, `probtrackx2` | `use_gpu=False` |

## venous_ct

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [ants_backend](snapshots/venous_ct/ants_backend.txt) | registration_engine=ANTS | 18 / 24 | `dcm2niix`, `fslmaths`, `robustfov`, `slicer_seg_endocranium.py` | — |
| [fsl_backend](snapshots/venous_ct/fsl_backend.txt) | registration_engine=FSL | 18 / 24 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov`, `slicer_seg_endocranium.py` | — |

## venous_mr

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [single_series_antspynet](snapshots/venous_mr/single_series_antspynet.txt) | deskull_engine=ANTSPYNET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=false; two_series=False; vein_detection_mode=SD | 12 / 15 | `dcm2niix`, `flirt`, `fslmaths` | — |
| [single_series_first](snapshots/venous_mr/single_series_first.txt) | deskull_engine=BET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=false; two_series=False; vein_detection_mode=FIRST | 12 / 15 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |
| [single_series_sd](snapshots/venous_mr/single_series_sd.txt) | deskull_engine=BET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=false; two_series=False; vein_detection_mode=SD | 12 / 15 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |
| [single_series_synth_backend](snapshots/venous_mr/single_series_synth_backend.txt) | deskull_engine=SYNTHSTRIP; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=true; two_series=False; vein_detection_mode=SD | 12 / 14 | `dcm2niix`, `fslmaths`, `mri_synthmorph`, `mri_synthstrip` | — |
| [single_series_synth_backend_limit_cores](snapshots/venous_mr/single_series_synth_backend_limit_cores.txt) | deskull_engine=SYNTHSTRIP; limit_synth_cores=true; max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=true; two_series=False; vein_detection_mode=SD | 12 / 14 | `dcm2niix`, `fslmaths`, `mri_synthmorph`, `mri_synthstrip` | — |
| [test_run](snapshots/venous_mr/test_run.txt) | deskull_engine=ANTSPYNET; synth_morph=False; test_run=True; two_series=False; vein_detection_mode=SD | 12 / 15 | `dcm2niix`, `flirt`, `fslmaths` | — |
| [two_series](snapshots/venous_mr/two_series.txt) | deskull_engine=BET; limit_synth_cores=false; max_cpu=4; multicore_node_limit=SOFT_CAP; synth_morph=false; two_series=True; vein_detection_mode=SD | 14 / 17 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |

