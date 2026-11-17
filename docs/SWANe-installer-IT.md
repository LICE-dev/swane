# Installare SWANe con l'installer (Ubuntu/macOS)

L'installer crea con un solo comando un ambiente completo e isolato di SWANe.
Non serve avere già Python: l'installer crea un ambiente conda con Python 3.12.

## 1. Lancio

Da un terminale:

```
curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash
```

> Lancialo da un terminale in cui **non** è attivo un ambiente conda il cui nome inizia con `swane` (es. `swane-env`):
> in caso contrario l'installer si ferma prima di cambiare qualsiasi cosa e chiede di eseguire `conda deactivate`.
> Su Mac non lanciarlo da un terminale che gira sotto Rosetta.

## 2. Cosa chiede

Prima di modificare qualsiasi cosa l'installer pone due domande:

1. **Quale conda usare**: elenca i conda trovati (escluso quello di FSL) più *Download and install a new Miniforge*.
   Rispondi `yes` per il primo oppure il numero di un altro; per un nuovo Miniforge chiede dove installarlo.
2. **Dove mettere gli ambienti di SWANe**: propone la cartella degli ambienti del conda scelto; rispondi `yes` o indica un'altra cartella.

Poi, a seconda del sistema:

- **FSL (facoltativo)**: l'installer mostra il link alla licenza di FSL (gratuito solo per uso non commerciale) e lo installa solo se scrivi `yes`.
- **Pacchetti di sistema Ubuntu**: su Linux con `apt` chiede una sola volta `sudo` per installare i pacchetti necessari a 3D Slicer, `tcsh`, `unzip` e il locale `en_US.UTF-8`.
  Se rispondi no, non viene eseguito nulla con `sudo` e il riepilogo finale elenca i comandi da lanciare a mano.

## 3. Cosa installa

- **`swane-env`**: ambiente conda con Python 3.12, SWANe e tutte le sue dipendenze Python (dcm2niix incluso),
  Graphviz se non già presente e, sui Mac Intel, TensorFlow da conda-forge.
- **`swane-fsl`** (facoltativo): una FSL minimale, nel suo ambiente conda, attiva solo mentre `swane-env` è attivo.
- **Launcher `swane`** in `~/.local/bin` (la cartella viene aggiunta al `PATH` nel file di avvio della shell, se manca).

## 4. Opzioni

Le opzioni si passano dopo `bash -s --`, per esempio:

```
curl -fsSL https://raw.githubusercontent.com/LICE-dev/swane/main/installer/install_swane.sh | bash -s -- --yes --no-fsl
```

| Opzione | Effetto |
| --- | --- |
| `--yes` | Risponde sì a tutto tranne che alla licenza FSL (usa il conda e la cartella proposti). |
| `--conda-root DIR` | Usa il conda installato in `DIR`, senza chiedere. |
| `--accept-fsl-license` | Accetta la licenza FSL senza chiedere. |
| `--no-fsl` | Non installa né configura FSL. |
| `--miniforge-prefix DIR` | Installa Miniforge in `DIR` e lo usa, senza chiedere. |
| `--install-dir DIR` | Cartella degli ambienti `swane-env` e `swane-fsl`, senza chiedere. |
| `-h`, `--help` | Mostra l'aiuto ed esce. |

## 5. Avvio

A fine installazione **apri un nuovo terminale** e lancia:

```
swane
```

Non serve attivare `swane-env`: il launcher lo fa da solo.

## 6. Cosa resta da installare a mano

L'installer **non** installa i programmi seguenti. Vanno aggiunti separatamente, prima o dopo SWANe,
seguendo le [Dependencies Guides](https://github.com/LICE-dev/swane/wiki/04-Dependencies-Guides).

| Software | Versione consigliata | A cosa serve |
| --- | --- | --- |
| [FreeSurfer](https://surfer.nmr.mgh.harvard.edu/fswiki/rel7downloads#A8.2.0_release/) | 8.2.0 | Analisi di superficie e segmentazioni |
| MATLAB Runtime per FreeSurfer (gratuito) | quella richiesta da FreeSurfer (lancia `./checkMCR.sh` in `freesurfer/bin`) | Moduli di segmentazione di ippocampo/amigdala |
| [3D Slicer](https://download.slicer.org/) | 5.12.4 | Visualizzazione dei risultati |

Il tab Home di SWANe mostra quali dipendenze sono state rilevate.
