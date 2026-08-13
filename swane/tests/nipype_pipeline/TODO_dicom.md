# TODO — test che richiedono DICOM specifici (o dati esterni)

Questo file elenca ciò che **non** è ancora coperto dai test light di
`swane/tests/nipype_pipeline/` e *perché*, così da pianificare come generare i
dati sintetici o come fornirli.

## Cosa è già coperto (senza DICOM)

- **engine/**, **nodes/**: logica Python pura, `aggregate_outputs`, rami
  "copy-only", generatori di nomi. Vedi `nodes/` e `engine/`.
- **workflows/**: *costruzione* del grafo (nodi presenti/assenti, backend
  FSL vs Synth, ramificazioni da preferenze). I builder ricevono le directory
  DICOM solo come stringhe (memorizzate su un nodo di conversione), quindi si
  costruiscono con cartelle vuote. **Nessuna esecuzione**, nessun DICOM.

## 1. Esecuzione end-to-end → serve DICOM specifico per modalità

La *costruzione* del grafo è coperta. Ciò che manca è **eseguire** i workflow
(far girare dcm2niix + FSL/FreeSurfer/Slicer sui dati). Serve un DICOM
sintetico che `dcm2niix` accetti e converta in un NIfTI con la geometria/numero
di volumi giusti per ciascuna modalità. Attualmente questo vive in
`swane/tests/integration/test_workflow.py` (marcato `heavy` + `requires_*`) e
usa DICOM reali.

Per ogni modalità serve un fantoccio DICOM con queste caratteristiche:

| Modalità (DataInput) | Cosa deve produrre dcm2niix | Note per la generazione |
|----------------------|-----------------------------|-------------------------|
| **T13D** (`ref_workflow`) | 1 volume 3D anatomico | volume singolo, header MR coerente |
| **FLAIR3D / T2 / MDC** (`linear_reg_workflow`) | 1 volume 3D | come sopra |
| **ASL / PET** (`func_map_workflow`) | 1 volume 3D funzionale | come sopra |
| **VENOUS_MR** (`venous_mr_workflow`) | 1 serie **multi-volume** (fasi) da splittare in `t`, oppure 2 serie separate | servono ≥2 volumi con `SliceLocation`/frame coerenti |
| **VENOUS_CT / SEEG_CT** (`venous_ct`, `seeg_ct`) | volume CT 3D | modalità CT; per venous_ct anche scansioni contrasto multiple |
| **DTI** (`dti_preproc_workflow`) | 4D diffusion **+ file `.bval` e `.bvec`** | il più difficile: dcm2niix deve riconoscere lo schema diffusion e generare bval/bvec |
| **fMRI** (`fMRI_preproc/task/resting`) | 4D **multi-volume** EPI con TR leggibile (`pixdim4`) | servono N volumi temporali e TR nell'header |

### Idee per generare i DICOM sintetici
- Estendere `swane/tests/helpers/dicom_factory.py` (già genera serie/volumi
  fantoccio con pydicom) per **scrivere pixel data reali** (piccoli volumi
  con contrasto), così `dcm2niix` produce NIfTI validi.
- Per **DTI**: popolare i tag diffusion (es. `(0019,100c)` b-value,
  `(0019,100e)` direzione per Siemens, o lo standard `DiffusionBValue`
  `(0018,9087)` / `DiffusionGradientOrientation`) su una serie multi-volume,
  finché dcm2niix emette `.bval`/`.bvec`. Da verificare con la versione di
  dcm2niix del CI.
- Per **fMRI/venous**: serie multi-volume con `NumberOfTemporalPositions` / TR
  (`RepetitionTime`) e più `SliceLocation` ripetute per volume.
- Alternativa: **non passare per dcm2niix** e testare i sotto-workflow a valle
  della conversione fornendo NIfTI sintetici direttamente ai nodi interni
  (richiede rifattorizzare i builder per accettare un NIfTI già convertito, o
  iniettare l'output del nodo di conversione).

## 2. Serve installazione/**dati** FSL (non DICOM)

Questi rami **non** si costruiscono senza file dati di FSL sul disco (path con
`File(exists=True)` o lettura di `os.environ["FSLDIR"]`):

- **`dti_preproc_workflow` con `tractography=True`**: legge
  `$FSLDIR/data/standard/MNI152_T1_1mm(.nii.gz|_brain.nii.gz)` e li passa come
  `in_file`/`reference` a FLIRT/FNIRT (esistenza validata alla costruzione).
- **`tractography_workflow`** (tratto reale): richiede la cartella protocolli
  XTRACT (`XTRACT_DATA_DIR/<tratto>_l|_r` con `seed.nii.gz`, `target*`, ecc.).
  Senza, il builder ritorna `None` (già testato).
- **`fMRI_resting_state_workflow` con `aroma=True`**: legge
  `$FSLDIR/data/standard/MNI152_T1_2mm_brain.nii.gz` e lo passa a FLIRT.

Opzione: fornire dei **NIfTI segnaposto** agli stessi path (monkeypatch di
`FSLDIR` verso una cartella temporanea con file MNI fittizi ma esistenti) per
testare almeno la *costruzione* di questi rami. Da valutare se ha senso o se
lasciarli all'integrazione con FSL reale.

## 3. Bug che blocca la costruzione (nessun DICOM necessario, serve fix)

- **`fMRI_task_workflow`**: la costruzione **fallisce** con la nipype installata
  (1.10): `Module <name>_modelestimate has no input called tcon_file`
  (`FILMGLS`). Il nome dell'input FILMGLS è cambiato/non esiste in questa
  versione. Va sistemato il builder (o allineata la versione di nipype) prima di
  poter aggiungere un test di costruzione per il task fMRI. Finché non è
  risolto, `fMRI_task_workflow` non è testabile nemmeno a livello di grafo.

## Riepilogo copertura workflow (costruzione)

| Workflow | Costruzione testata | Note |
|----------|--------------------|------|
| ref, linear_reg, nonlinear_reg | ✅ | backend FSL/Synth |
| freesurfer, freesurfer_asymmetry_index | ✅ | step + hippo |
| func_map (ASL/PET), venous_mr | ✅ | FreeSurfer/AI/detection |
| venous_ct, seeg_ct | ✅ | |
| flat1 | ✅ | backend FSL/Synth |
| dti_preproc | ✅ (no tractography) | ramo tractography → §2 |
| fMRI_preproc | ✅ | |
| fMRI_resting_state | ✅ (aroma off) | ramo aroma → §2 |
| tractography | ✅ (solo guardia → None) | tratto reale → §2 |
| **fMRI_task** | ❌ | §3 bug FILMGLS |
