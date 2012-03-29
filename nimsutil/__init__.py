# @author:  Gunnar Schaefer

from nimsutil import *

try:
    from dicomutil import *
except:
    print 'Warning: could not import dicomutil module'

try:
    import pfile
except:
    print 'Warning: could not import pfile module'
