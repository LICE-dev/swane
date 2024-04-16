# slicerpython script for module checking
# Warning: slicer library is not required beacuse the script is executed in Slicer environment

import sys

# Check FreeSurfer imported module into 3D Slicer 
if hasattr(slicer.moduleNames, 'FreeSurferImporter'):
    print('MODULE FOUND')
sys.exit(0)
