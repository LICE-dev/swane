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
- **matrix/**: *matrice di setting* + **snapshot golden** deterministici. Per
  ogni workflow factory costruisce il grafo su tutte le combinazioni di
  preferenze rilevanti (incluso **CUDA on/off** per DTI) e salva uno snapshot
  testuale leggibile in `matrix/snapshots/<workflow>/<scenario>.txt`, usato sia
  come guardia di regressione sia come output da controllare a mano. Vedi
  `matrix/README.md`. Rigenerabile con `SWANE_SNAPSHOT_UPDATE=1`; report HTML
  navigabile con `python matrix/generate_report.py`.
  > NB: i workflow importano il pacchetto Python `dcm2niix` (binario incluso,
  > dichiarato in `setup.py`). Se manca nell'ambiente, i test `workflows/` e
  > `matrix/` non si *raccolgono* nemmeno: `pip install -e .` lo installa.

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

## 2. Rami che leggono **dati** FSL alla costruzione (non DICOM)

Questi rami leggono file dati di FSL sul disco alla costruzione (path con
`File(exists=True)` o lettura di `os.environ["FSLDIR"]`):

- **`dti_preproc_workflow` con `tractography=True`**: legge
  `$FSLDIR/data/standard/MNI152_T1_1mm(.nii.gz|_brain.nii.gz)` e li passa come
  `in_file`/`reference` a FLIRT/FNIRT (esistenza validata alla costruzione);
  aggiunge BEDPOSTX + registrazione MNI→reference.
- **`tractography_workflow`** (tratto reale): richiede la cartella protocolli
  XTRACT (`XTRACT_DATA_DIR/<tratto>_l|_r` con `seed.nii.gz`, `target*`, ecc.).
- **`fMRI_resting_state_workflow` con `aroma=True`**: legge
  `$FSLDIR/data/standard/MNI152_T1_2mm_brain.nii.gz` e lo passa a FLIRT.

**Costruzione: ora coperta** dalla matrice, nell'ottica "il box di riferimento
ha tutti i tool installati". Ognuno di questi rami ha uno scenario snapshot
(`dti_preproc/new_eddy_tractography`, `tractography/cst_real_graph`,
`fmri_resting_state/aroma_on`) che si costruisce e si confronta col golden
**quando i dati FSL sono presenti**, e degrada a *skip* (mai fallimento) su un
box che ne è privo (helper `matrix/conftest.require_fsl_data`). I path FSL negli
snapshot sono riscritti a `<FSLDIR>` per restare deterministici.

**Cosa resta per §2 → l'esecuzione**, non la costruzione: far girare davvero
questi rami (bedpostx, probtrackx, ICA-AROMA) e — punto specifico — verificare
l'**equivalenza CPU vs GPU** dei percorsi `use_gpu`/`use_cuda` (eddy, bedpostx,
probtrackx), che richiede hardware GPU + FSL reale (vedi §4).

## 3. Bug che blocca la costruzione (RISOLTO — era l'ambiente, non nipype)

- ~~**`fMRI_task_workflow`**: la costruzione fallisce (...) `Module
  <name>_modelestimate has no input called tcon_file` (`FILMGLS`)~~. Non era
  un problema di nipype 1.10 né del builder: `FILMGLS` sceglie la sua
  `input_spec` **all'import** in base a `nipype.interfaces.fsl.base.
  Info.version()`; su una macchina senza FSL installato (es. la macchina
  Windows su cui questo bug era stato osservato) quella versione risulta
  `None` e nipype ripiega silenziosamente su una `input_spec` più vecchia,
  priva di `tcon_file`/`fcon_file`. Con FSL >= 5.0.7 reale installato il
  costrutto funziona senza modifiche al builder. Fix in
  `swane/tests/conftest.py`: quando la rilevazione reale di FSL non c'è, si
  forza `Info.version()` (solo per le classi `nipype.interfaces.fsl.*`) a
  riportare una versione FSL moderna, così i test di costruzione si
  comportano allo stesso modo con o senza FSL reale installato; stessa
  sistemazione per `FSLOUTPUTTYPE` (forzato a `NIFTI_GZ`, il default reale di
  FSL, se non già impostato — prima ripiegava silenziosamente su `NIFTI`).
  Matrice+snapshot aggiunta in `matrix/test_fmri_task_matrix.py`
  (`snapshots/fmri_task/`), sweep su `block_design` (RARA vs RARB, che
  aggiunge un secondo contrasto/ramo di clustering).

## 4. Validazione scientifica degli output (oltre "gira")

I §1–§3 riguardano l'infrastruttura per arrivare a **eseguire** i workflow. Ma
"il grafo si costruisce" ≠ "il workflow gira" ≠ "il risultato è **corretto**".
I test matrix di `matrix/` coprono solo il primo livello; il §1 porta al secondo
("gira: nessun crash, output generati"). Questa sezione traccia il terzo livello,
che **non è ancora coperto da nessun test**: verificare che gli output siano
scientificamente plausibili, non solo presenti.

Serve un ambiente neuroimaging reale (Linux/macOS + FSL/FreeSurfer/Slicer) e dei
**riferimenti de-identificati "buoni"** (output di una run verificata a mano) da
tenere **fuori dal repo** — mai committare risultati clinici o dati paziente
(vedi `AGENTS.md`).

Cosa confrontare, per ogni output rilevante:

- **Geometria/header**: affine, orientamento, voxel size e dimensioni preservati
  dove il nodo non deve trasformarli; nessun flip/rotazione spuria.
- **Direzione delle registrazioni**: reference vs moving corretti (soprattutto
  reference/atlas e le catene di warp/inverse-warp); l'output finisce nello
  spazio atteso (T13D ref, MNI, spazio diffusione, ecc.).
- **Interpolazione**: `trilinear`/spline per immagini scalari, `nearestneighbour`
  per maschere/label/segmentazioni; nessuna label "sporcata" da interpolazione.
- **Skull strip / maschere**: cervello plausibile (né tagliato né con cranio
  residuo) al variare di `bet_thr`/bias/SynthStrip.
- **Valori e range**: soglie, unità, TR/`pixdim4`, numero e ordine dei volumi,
  z-score/AI nei range attesi; seed e conteggi coerenti.
- **Equivalenza CPU vs GPU/CUDA**: i percorsi `use_cuda`/`use_gpu` (eddy,
  bedpostx, probtrackx) devono dare output equivalenti a livello di contratto,
  non solo "terminare".
- **Consumatori a valle**: DataSink (nomi/cartelle risultato), export, Slicer e
  visualizzazione ricevono i file col contratto atteso.

Approccio suggerito: a valle del §1, per un sottoinsieme di modalità/scenari,
confrontare gli output contro i riferimenti con tolleranze esplicite (es.
`nibabel`/`numpy.allclose` su affine e dati, controllo header, diff di maschere)
— separando sempre la **regressione software** (l'output non è cambiato tra due
versioni di SWANe) dalla **validazione clinica** (l'output è giusto per il
paziente), che resta responsabilità umana.

## Riepilogo copertura workflow (costruzione)

| Workflow | Costruzione testata | Matrice+snapshot | Note |
|----------|--------------------|------------------|------|
| ref, linear_reg, nonlinear_reg | ✅ | ✅ | backend FSL/Synth, bias/thr, coverage |
| freesurfer, freesurfer_asymmetry_index | ✅ | ✅ | step + hippo + synth recon-all |
| func_map (ASL/PET), venous_mr | ✅ | ✅ | FreeSurfer/AI/detection/serie |
| venous_ct, seeg_ct | ✅ | ✅ | contrasto/soglie |
| flat1 | ✅ | ✅ | backend FSL/Synth |
| dti_preproc | ✅ | ✅ (**CUDA on/off**, eddy, core-limit, tractography) | ramo tractography coperto se dati FSL presenti; esecuzione GPU → §2 |
| fMRI_preproc | ✅ | ✅ | slice timing, trim volumi |
| fMRI_resting_state | ✅ | ✅ (melodic + aroma) | ramo aroma coperto se dati FSL presenti |
| tractography | ✅ | ✅ (grafo cst reale + guardia nome) | tratto reale coperto se XTRACT presente; esecuzione GPU → §2 |
| fMRI_task | ✅ | ✅ | §3 risolto — sweep `block_design` |
