# @author:  Gunnar Schaefer

import os
import glob


for mod in [os.path.basename(f)[:-3] for f in glob.glob(os.path.dirname(__file__) + '/nims*.py')]:
    __import__(mod, globals())
del f, mod

parse = nimsdata.NIMSData.parse
