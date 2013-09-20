#!/usr/bin/env python
#
# @author:  Robert Dougherty

import transaction
import numpy as np

from nimsgears.model import *
from nimsdata import nimsimage

class DummyImage(nimsimage.NIMSImage):
    def __init__(self, te, psd_type, is_dwi, fov, mm_per_vox, num_timepoints):
        import numpy as np
        self.te = te
        self.psd_type = psd_type
        self.is_dwi = is_dwi
        self.fov = np.fromstring(fov[1:-1], sep=',')
        self.mm_per_vox = np.fromstring(mm_per_vox[1:-1], sep=',')
        self.num_timepoints = num_timepoints

epochs = Epoch.query.filter(Epoch.scan_type=='anatomy').all()
ids = [e.id for e in epochs]

for id in ids:
    e = Epoch.query.filter(Epoch.id==id).first()
    # fix bad fov's
    #fov = np.fromstring(e.fov[1:-1], sep=',')
    #if fov.size==1:
    #    fov = np.array([fov[0],fov[0]])
    #fov[fov<5.] *= 100.
    #e.fov = unicode(str(list(fov.round(3))))
    #e.fov = unicode('[%0.2f, %0.2f]' % (fov[0], fov[1]))
    psd_type = nimsimage.infer_psd_type(e.psd)
    # hack to infer dwi. (All dwi's at CNI use some variant of the epi2 psd.)
    if 'epi' in psd_type and 'epi2' in e.psd:
        is_dwi = True
    else:
        is_dwi = False
    di = DummyImage(e.te, psd_type, is_dwi, e.fov, e.mm_per_vox, e.num_timepoints)
    e.scan_type = di.infer_scan_type()
    print e.id, e.scan_type, e.fov
    transaction.commit()


