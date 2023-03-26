#CHECK PRESENCE OF FREESURFER EXTENSION IN SLICER!
import sys
if hasattr(slicer.moduleNames, 'FreeSurferImporter'):
    print('MODULE FOUND')
sys.exit(0)
