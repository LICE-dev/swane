# SWANe workflow settings matrix

Overview of 66 construction scenarios across 14 workflow families. Each row is one setting combination; follow the *snapshot* link for the full graph (nodes, commands, flags, wiring).

> Generated from the golden snapshots by `python swane/tests/nipype_pipeline/matrix/generate_report.py` — do not edit by hand. Regenerate after refreshing the snapshots (`SWANE_SNAPSHOT_UPDATE=1 pytest .../matrix`).

[dti_preproc](#dti-preproc) · [flat1](#flat1) · [fmri_preproc](#fmri-preproc) · [fmri_resting_state](#fmri-resting-state) · [fmri_task](#fmri-task) · [freesurfer](#freesurfer) · [func_map](#func-map) · [linear_reg](#linear-reg) · [nonlinear_reg](#nonlinear-reg) · [ref](#ref) · [seeg_ct](#seeg-ct) · [tractography](#tractography) · [venous_ct](#venous-ct) · [venous_mr](#venous-mr)

## dti_preproc

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [new_eddy_cpu_hardcap](snapshots/dti_preproc/new_eddy_cpu_hardcap.txt) | cuda=false; max_cpu=4; multicore_node_limit=HARD_CAP; old_eddy_correct=false; synth_morph=False; synth_strip=False; tractography=false | 12 / 20 | `bet`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False` |
| [new_eddy_cpu_softcap](snapshots/dti_preproc/new_eddy_cpu_softcap.txt) | cuda=false; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; synth_strip=False; tractography=false | 12 / 20 | `bet`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False` |
| [new_eddy_cuda](snapshots/dti_preproc/new_eddy_cuda.txt) | cuda=true; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; synth_strip=False; tractography=false | 12 / 20 | `bet`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy`, `flirt` | `use_cuda=True` |
| [new_eddy_tractography](snapshots/dti_preproc/new_eddy_tractography.txt) | cuda=false; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; synth_strip=False; tractography=true | 13 / 25 | `bedpostx`, `bet`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False`, `use_gpu=False` |
| [old_eddy_correct](snapshots/dti_preproc/old_eddy_correct.txt) | cuda=false; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=true; synth_morph=False; synth_strip=False; tractography=false | 11 / 16 | `bet`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_correct`, `flirt` | — |
| [test_run](snapshots/dti_preproc/test_run.txt) | cuda=false; max_cpu=4; multicore_node_limit=SOFT_CAP; old_eddy_correct=false; synth_morph=False; synth_strip=False; test_run=True; tractography=true | 13 / 25 | `bedpostx`, `bet`, `convert_xfm`, `dcm2niix`, `dtifit`, `eddy_openmp`, `flirt` | `use_cuda=False`, `use_gpu=False` |

## flat1

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [fsl_backend](snapshots/flat1/fsl_backend.txt) | synth_morph=false | 30 / 44 | `applywarp`, `fast`, `fslmaths` | — |
| [fsl_backend_test_run](snapshots/flat1/fsl_backend_test_run.txt) | synth_morph=false; test_run=True | 30 / 44 | `applywarp`, `fast`, `fslmaths` | — |
| [synthmorph_backend](snapshots/flat1/synthmorph_backend.txt) | synth_morph=true | 30 / 44 | `fast`, `fslmaths`, `mri_synthmorph` | — |
| [synthmorph_backend_test_run](snapshots/flat1/synthmorph_backend_test_run.txt) | synth_morph=true; test_run=True | 30 / 44 | `fast`, `fslmaths`, `mri_synthmorph` | — |

## fmri_preproc

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [slicetiming_interleaved](snapshots/fmri_preproc/slicetiming_interleaved.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=INTERLEAVED | 27 / 41 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |
| [slicetiming_unknown](snapshots/fmri_preproc/slicetiming_unknown.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=UNKNOWN | 26 / 39 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `susan` | — |
| [slicetiming_up](snapshots/fmri_preproc/slicetiming_up.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=UP | 27 / 41 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |
| [test_run](snapshots/fmri_preproc/test_run.txt) | TR=2.0; del_end_vols=0; del_start_vols=0; hpcutoff=30; n_vols=100; slice_timing=UP; test_run=True | 27 / 41 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |
| [trim_start_end_vols](snapshots/fmri_preproc/trim_start_end_vols.txt) | TR=3.0; del_end_vols=3; del_start_vols=5; hpcutoff=50; n_vols=120; slice_timing=UP | 27 / 41 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `slicetimer`, `susan` | — |

## fmri_resting_state

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [aroma_on](snapshots/fmri_resting_state/aroma_on.txt) | aroma=true; melodic_dim=0; melodic_thr=0.5 | 44 / 75 | `applywarp`, `bet`, `convertwarp`, `dcm2niix`, `flirt`, `fnirt`, `fsl_regfilt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |
| [melodic_auto_dim](snapshots/fmri_resting_state/melodic_auto_dim.txt) | aroma=false; melodic_dim=0; melodic_thr=0.5 | 31 / 49 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |
| [melodic_fixed_dim](snapshots/fmri_resting_state/melodic_fixed_dim.txt) | aroma=false; melodic_dim=30; melodic_thr=0.9 | 31 / 49 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |
| [test_run](snapshots/fmri_resting_state/test_run.txt) | aroma=true; melodic_dim=0; melodic_thr=0.5; test_run=True | 44 / 75 | `applywarp`, `bet`, `convertwarp`, `dcm2niix`, `flirt`, `fnirt`, `fsl_regfilt`, `fslmaths`, `mcflirt`, `melodic`, `susan` | — |

## fmri_task

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [single_contrast_rara](snapshots/fmri_task/single_contrast_rara.txt) | block_design=RARA; rest_duration=30; task_a_name=Task_A; task_b_name=Task_B; task_duration=30 | 42 / 86 | `bet`, `cluster`, `dcm2niix`, `feat_model`, `film_gls`, `flirt`, `fslmaths`, `mcflirt`, `smoothest`, `susan` | — |
| [test_run](snapshots/fmri_task/test_run.txt) | block_design=RARA; rest_duration=30; task_a_name=Task_A; task_b_name=Task_B; task_duration=30; test_run=True | 42 / 86 | `bet`, `cluster`, `dcm2niix`, `feat_model`, `film_gls`, `flirt`, `fslmaths`, `mcflirt`, `smoothest`, `susan` | — |
| [two_contrasts_rarb](snapshots/fmri_task/two_contrasts_rarb.txt) | block_design=RARB; rest_duration=30; task_a_name=Task_A; task_b_name=Task_B; task_duration=30 | 50 / 116 | `bet`, `cluster`, `dcm2niix`, `feat_model`, `film_gls`, `flirt`, `fslmaths`, `mcflirt`, `smoothest`, `susan` | — |

## freesurfer

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [autorecon_pial](snapshots/freesurfer/autorecon_pial.txt) | hippo_amyg_labels=False; max_cpu=4; multicore_node_limit=SOFT_CAP; step=AUTORECON_PIAL; synth_reconall=false | 11 / 16 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [disabled_returns_none](snapshots/freesurfer/disabled_returns_none.txt) | hippo_amyg_labels=False; max_cpu=4; multicore_node_limit=SOFT_CAP; step=DISABLED; synth_reconall=false | None | — | — |
| [reconall](snapshots/freesurfer/reconall.txt) | hippo_amyg_labels=False; max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; synth_reconall=false | 12 / 18 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [reconall_hippo](snapshots/freesurfer/reconall_hippo.txt) | hippo_amyg_labels=True; max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; synth_reconall=false | 15 / 25 | `fslmaths`, `mri_vol2vol`, `recon-all`, `segmentHA_T1.sh` | — |
| [reconall_synth_tools](snapshots/freesurfer/reconall_synth_tools.txt) | hippo_amyg_labels=False; max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; synth_reconall=true | 12 / 18 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [reconall_test_run](snapshots/freesurfer/reconall_test_run.txt) | max_cpu=4; multicore_node_limit=SOFT_CAP; step=RECONALL; test_run=True | 12 / 18 | `fslmaths`, `mri_vol2vol`, `recon-all` | — |
| [synthseg](snapshots/freesurfer/synthseg.txt) | hippo_amyg_labels=False; max_cpu=4; multicore_node_limit=SOFT_CAP; step=SYNTHSEG; synth_reconall=false | 8 / 11 | `fslmaths`, `mri_synthseg`, `mri_vol2vol` | — |
| [synthseg_test_run](snapshots/freesurfer/synthseg_test_run.txt) | max_cpu=4; multicore_node_limit=SOFT_CAP; step=SYNTHSEG; test_run=True | 8 / 11 | `fslmaths`, `mri_synthseg`, `mri_vol2vol` | — |

## func_map

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
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
| [flair2d_non_volumetric](snapshots/linear_reg/flair2d_non_volumetric.txt) | bias_field_correction=False; config=None; is_partial_coverage=False; is_volumetric=False; synth_morph=false; synth_strip=false | 11 / 18 | `bet`, `dcm2niix`, `flirt`, `robustfov` | — |
| [flair3d_bias](snapshots/linear_reg/flair3d_bias.txt) | bias_field_correction=True; config=FLAIR3D; is_partial_coverage=False; is_volumetric=True; synth_morph=false; synth_strip=false | 13 / 26 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |
| [flair3d_no_bias](snapshots/linear_reg/flair3d_no_bias.txt) | bias_field_correction=False; config=FLAIR3D; is_partial_coverage=False; is_volumetric=True; synth_morph=false; synth_strip=false | 11 / 18 | `bet`, `dcm2niix`, `flirt`, `robustfov` | — |
| [flair3d_synth_backend](snapshots/linear_reg/flair3d_synth_backend.txt) | bias_field_correction=True; config=FLAIR3D; is_partial_coverage=False; is_volumetric=True; synth_morph=true; synth_strip=true | 13 / 24 | `dcm2niix`, `fslmaths`, `mri_synthmorph`, `mri_synthstrip`, `robustfov` | — |
| [mdc_bias](snapshots/linear_reg/mdc_bias.txt) | bias_field_correction=True; config=MDC; is_partial_coverage=False; is_volumetric=True; synth_morph=false; synth_strip=false | 13 / 26 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |
| [t2cor_partial_coverage](snapshots/linear_reg/t2cor_partial_coverage.txt) | bias_field_correction=False; config=None; is_partial_coverage=True; is_volumetric=True; synth_morph=false; synth_strip=false | 10 / 16 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |
| [test_run](snapshots/linear_reg/test_run.txt) | bias_field_correction=True; config=FLAIR3D; is_partial_coverage=False; is_volumetric=True; synth_morph=False; synth_strip=False; test_run=True | 13 / 26 | `bet`, `dcm2niix`, `flirt`, `fslmaths`, `robustfov` | — |

## nonlinear_reg

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [fsl_backend](snapshots/nonlinear_reg/fsl_backend.txt) | synth_morph=false | 6 / 10 | `applywarp`, `flirt`, `fnirt`, `invwarp` | — |
| [fsl_backend_test_run](snapshots/nonlinear_reg/fsl_backend_test_run.txt) | synth_morph=false; test_run=True | 6 / 10 | `applywarp`, `flirt`, `fnirt`, `invwarp` | — |
| [synthmorph_backend](snapshots/nonlinear_reg/synthmorph_backend.txt) | synth_morph=true | 4 / 5 | `mri_synthmorph` | — |
| [synthmorph_backend_test_run](snapshots/nonlinear_reg/synthmorph_backend_test_run.txt) | synth_morph=true; test_run=True | 4 / 5 | `mri_synthmorph` | — |

## ref

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [bet_bias_thr0](snapshots/ref/bet_bias_thr0.txt) | bet_bias_correction=true; bet_thr=0.0; synth_strip=false | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |
| [bet_default](snapshots/ref/bet_default.txt) | bet_bias_correction=false; bet_thr=0.3; synth_strip=false | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |
| [bet_thr_high](snapshots/ref/bet_thr_high.txt) | bet_bias_correction=false; bet_thr=1.0; synth_strip=false | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |
| [synthstrip](snapshots/ref/synthstrip.txt) | bet_bias_correction=false; bet_thr=0.3; synth_strip=true | 8 / 12 | `dcm2niix`, `fslmaths`, `mri_synthstrip`, `robustfov` | — |
| [test_run](snapshots/ref/test_run.txt) | bet_bias_correction=false; bet_thr=0.3; synth_strip=False; test_run=True | 8 / 12 | `bet`, `dcm2niix`, `fslmaths`, `robustfov` | — |

## seeg_ct

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [default](snapshots/seeg_ct/default.txt) | electrode_threshold=2000; erode_kernel_size=5 | 13 / 16 | `dcm2niix`, `flirt`, `fslmaths` | — |
| [tuned_threshold_kernel](snapshots/seeg_ct/tuned_threshold_kernel.txt) | electrode_threshold=2500; erode_kernel_size=8 | 13 / 16 | `dcm2niix`, `flirt`, `fslmaths` | — |

## tractography

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [cst_real_graph](snapshots/tractography/cst_real_graph.txt) | cuda=false; tract=cst; xtract_data=present | 13 / 21 | `applywarp`, `probtrackx2` | `use_gpu=False` |
| [cst_real_graph_test_run](snapshots/tractography/cst_real_graph_test_run.txt) | cuda=false; test_run=True; tract=cst; xtract_data=present | 13 / 21 | `applywarp`, `probtrackx2` | `use_gpu=False` |

## venous_ct

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [auto_threshold_two_contrast](snapshots/venous_ct/auto_threshold_two_contrast.txt) | contrast_series=2; skull_threshold=-1 | 18 / 24 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov`, `slicer_seg_endocranium.py` | — |
| [fixed_threshold_two_contrast](snapshots/venous_ct/fixed_threshold_two_contrast.txt) | contrast_series=2; skull_threshold=1500 | 18 / 24 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov`, `slicer_seg_endocranium.py` | — |
| [single_contrast](snapshots/venous_ct/single_contrast.txt) | contrast_series=1; skull_threshold=-1 | 18 / 24 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov`, `slicer_seg_endocranium.py` | — |
| [test_run](snapshots/venous_ct/test_run.txt) | contrast_series=1; segment_endocranium_iteration_user_value=10; segment_endocranium_oversampling_user_value=3.0; skull_threshold=-1; test_run=True | 18 / 24 | `dcm2niix`, `flirt`, `fslmaths`, `robustfov`, `slicer_seg_endocranium.py` | — |

## venous_mr

| scenario | settings | nodes/edges | commands | GPU |
|----------|----------|-------------|----------|-----|
| [single_series_first](snapshots/venous_mr/single_series_first.txt) | synth_morph=false; synth_strip=false; two_series=False; vein_detection_mode=FIRST | 12 / 15 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |
| [single_series_sd](snapshots/venous_mr/single_series_sd.txt) | synth_morph=false; synth_strip=false; two_series=False; vein_detection_mode=SD | 12 / 15 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |
| [single_series_synth_backend](snapshots/venous_mr/single_series_synth_backend.txt) | synth_morph=true; synth_strip=true; two_series=False; vein_detection_mode=SD | 12 / 14 | `dcm2niix`, `fslmaths`, `mri_synthmorph`, `mri_synthstrip` | — |
| [test_run](snapshots/venous_mr/test_run.txt) | synth_morph=False; synth_strip=False; test_run=True; two_series=False; vein_detection_mode=SD | 12 / 15 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |
| [two_series](snapshots/venous_mr/two_series.txt) | synth_morph=false; synth_strip=false; two_series=True; vein_detection_mode=SD | 14 / 17 | `bet`, `dcm2niix`, `flirt`, `fslmaths` | — |

