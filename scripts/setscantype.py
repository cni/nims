#!/usr/bin/env python
#
# @author:  Robert Dougherty

import transaction
import numpy as np

from nimsgears.model import *
from nimsdata import nimsimage

class DummyImage(nimsimage.NIMSImage):
    def __init__(self, te, psd_type, is_dwi, fov, mm_per_vox, num_timepoints):
        self.te = te
        self.psd_type = psd_type
        self.is_dwi = is_dwi
        self.fov = fov
        self.mm_per_vox = mm_per_vox
        self.num_timepoints = num_timepoints

epochs = Epoch.query.all()
ids = [e.id for e in epochs]

for id in ids:
    e = Epoch.query.filter(Epoch.id==id).first()
    # fix bad fov's
    fov = np.fromstring(e.fov[1:-1], sep=',')
    fov[fov<5.] *= 100.
    e.fov = unicode(str(fov))
    psd_type = nimsimage.infer_psd_type(e.psd)
    # hack to infer dwi. (All dwi's at CNI use some variant of the epi2 psd.)
    if psd_type=='epi' and 'epi2' in e.psd:
        is_dwi = True
    else:
        is_dwi = False
    di = DummyImage(e.te, psd_type, is_dwi, e.fov, e.mm_per_vox, e.num_timepoints)
    e.scan_type = di.infer_scan_type()
    print e.id, e.scan_type, e.fov
    transaction.commit()


