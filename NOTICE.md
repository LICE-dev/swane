## Slicer --no-main-window compatibility code

This project makes use of procedures and concepts derived from SlicerMorph
(https://github.com/SlicerMorph/SlicerMorph), which is licensed under the 
BSD 2-Clause License.
These concepts have been adapted and reimplemented in
`swane/workers/slicer_seg_endocranium.py` to provide compatibility
with the --no-main-window 3D Slicer argument.


**License**: BSD 2-Clause License

**Copyright**: (c) 2019, SlicerMorph Project All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

---
## Nipype derived code

This project makes use of code, procedures and concepts derived from 
NiPype (https://github.com/nipy/nipype), licensed under the Apache License, Version 2.0.
This code has been modified from the original Nipype implementation
to support custom command-line handling and integration with 3D Slicer and 
is included in `slicer/nipype_pipeline` directory.


**License**: Apache License, Version 2.0

**Copyright**: (c) 2009-2016, Nipype developers

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Prior to release 0.12, Nipype was licensed under a BSD license.

---
## Images derived from ICBM 2009c Nonlinear Symmetric Atlas

This project includes images derived from ICBM 2009c Nonlinear Symmetric 
Atlas (https://nist.mni.mcgill.ca/icbm-152-nonlinear-atlases-2009/).
These images are internalized under `swane/resources/atlas/` (formerly
distributed as the separate `swane_supplement` package, now merged into this
repository).


**Copyright**: (c) 1993-2004 Louis Collins, McConnell Brain Imaging Centre, Montreal 
Neurological Institute, McGill University

**License**: Permission to use, copy, modify, and distribute this software and
its documentation for any purpose and without fee is hereby granted, provided
that the above copyright notice appear in all copies. The authors and McGill
University make no representations about the suitability of this software for
any purpose. It is provided "as is" without express or implied warranty. The
authors are not responsible for any data loss, equipment damage, property
loss, or injury to subjects or patients resulting from the use or misuse of
this software package.

Like the HCP842 atlas below, this is a permissive, attribution-style license:
it carries no acceptance flow of its own and is not part of the first-launch
consent gate. It is documented here, and linked from the Home tab's Atlases
column, for attribution.

---

## FLAT1 reference maps

The FLAT1 workflow's z-score pipeline uses a set of statistical reference
templates (cerebellum mask, cortex mask, and mean/std FLAIR and extension
maps), internalized under `swane/resources/atlas/FLAT1/`. These are
SWANe/LICE's own derived data, not third-party material, and are covered by
this repository's own root `LICENSE` (MIT) like the rest of the codebase.

---

## fsaverage (FreeSurfer)

SWANe's test suite builds a synthetic subject ("phantom") for automated
testing, and its tissue-class map generator
(`swane/tests/helpers/phantom/`) reads the `fsaverage` subject shipped with a
locally installed FreeSurfer. `fsaverage` is never bundled with or committed
to this repository; it is only read, at test time, from the user's own
FreeSurfer installation, under the same FreeSurfer Software License Agreement
already listed above.

---
## External neuroimaging tools orchestrated by SWANe

SWANe orchestrates the following external tools as separate processes. SWANe
does not include or redistribute these tools' code; users install them
separately and must comply with each tool's own license:

- **FSL (FMRIB Software Library)** — free for non-commercial use; commercial use
  requires a license from Oxford University Innovation.
  https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html
- **FreeSurfer** — distributed under the FreeSurfer Software License Agreement;
  free, restricts commercial use, requires registration for a license key.
  https://github.com/freesurfer/freesurfer/blob/dev/LICENSE.txt
- **3D Slicer** — Slicer License (BSD-style).
  https://github.com/Slicer/Slicer/blob/main/License.txt
- **dcm2niix** — BSD 2-Clause License.
  https://github.com/rordenlab/dcm2niix/blob/master/license.txt

At first launch (and whenever a tool's detected version changes), SWANe shows the
license of each detected tool and requires explicit acceptance. For display,
SWANe reads the license installed on the user's system when available, otherwise
fetches the current license online, otherwise falls back to a bundled copy under
`swane/licenses/`. These bundled copies are license text only (no tool code) and
are refreshed from upstream before releases via `tools/refresh_bundled_licenses.py`.

---
## dipy (tractography engine)

SWANe's dipy-based tractography engine depends on the `dipy` pip package.
SWANe does not modify or redistribute dipy's source; it is installed as a
regular Python dependency (see `setup.py`).

**License**: BSD 3-Clause License.
https://github.com/dipy/dipy/blob/master/LICENSE

Like the other detected third-party tools, SWANe shows dipy's license at first
launch (and whenever its detected version changes) and requires explicit
acceptance, following the same mechanism described above.

---
## HCP842 bundle atlas

SWANe's dipy tractography engine fetches the HCP842 whole-brain bundle atlas
(`Atlas_80_Bundles`, distributed via dipy's `fetch_bundle_atlas_hcp842`) at
first use, to align each subject's tractogram and recognise its bundles
(RecoBundles). The atlas is data, not software, and is downloaded on demand
into the user's local dipy data directory; it is never bundled with or
committed to this repository.

**License**: Creative Commons Attribution 4.0 International (CC BY 4.0).

**Copyright**: © Eleftherios Garyfallidis.

CC BY 4.0 requires attribution, which this notice provides; unlike the
software licenses above, it carries no acceptance flow of its own.