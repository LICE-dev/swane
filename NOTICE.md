## Slicer --no-main-window compatibility code

This project makes use of procedures and concepts derived from SlicerMorph (https://github.com/SlicerMorph/SlicerMorph),
which is licensed under the BSD 2-Clause License.
These concepts have been adapted and reimplemented in
`swane/workers/slicer_seg_endocranium.py` to provide compatibility
with the --no-main-window 3D Slicer argument.


**License**: BSD 2-Clause License

**Copyright**: Copyright (c) 2019, SlicerMorph Project All rights reserved.

---
### BSD 2-Clause License
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

## Nipype derived code

This project makes use of code, procedures and concepts derived from 
NiPype (https://github.com/nipy/nipype), licensed under the Apache License, Version 2.0.
This code has been modified from the original Nipype implementation
to support custom command-line handling and integration with 3D Slicer and 
is included in `slicer/nipype_pipeline` directory.


**License**: Apache License, Version 2.0

**Copyright**: Copyright (c) 2009-2016, Nipype developers

---
### Apache License, Version 2.0
Copyright (c) 2009-2016, Nipype developers

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