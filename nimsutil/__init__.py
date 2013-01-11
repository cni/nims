# @author:  Gunnar Schaefer

from nimsutil import *

datatypes = []

try:
    import pyramid
except:
    print 'Warning: could not import pyramid module'

try:
    import dicomutil
except:
    print 'Warning: could not import dicomutil module'
else:
    datatypes += [dicomutil.DicomFile]

try:
    import pfile
except:
    print 'Warning: could not import pfile module'
else:
    datatypes += [pfile.PFile]

try:
    import physio
except:
    print 'Warning: could not import physio module'
else:
    datatypes += [physio.PhysioData]
