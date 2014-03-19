#!/usr/bin/env python
#
# @author:  Robert Dougherty

import transaction
import numpy as np

from nimsgears.model import *
from nimsdata import nimsmrdata

class DummyImage(nimsmrdata.NIMSMRData):
    def __init__(self, te, psd_type, is_dwi, fov, mm_per_vox, num_timepoints):
        import numpy as np
        self.te = te
        self.psd_type = psd_type
        self.is_dwi = is_dwi
        self.fov = np.fromstring(fov[1:-1], sep=',')
        self.mm_per_vox = np.fromstring(mm_per_vox[1:-1], sep=',')
        self.num_timepoints = num_timepoints



ids = [e.id for e in Epoch.query.filter(Epoch.scan_type==u'EPI').all()]

for id in ids:
    e = Epoch.query.filter(Epoch.id==id).first()
    fov = np.fromstring(e.fov[1:-1], sep=',')
    mm_per_vox = np.fromstring(e.mm_per_vox[1:-1], sep=',')
    # fix bad fov's
    #fov = np.fromstring(e.fov[1:-1], sep=',')
    #if fov.size==1:
    #    fov = np.array([fov[0],fov[0]])
    #fov[fov<5.] *= 100.
    #e.fov = unicode(str(list(fov.round(3))))
    #e.fov = unicode('[%0.2f, %0.2f]' % (fov[0], fov[1]))
    psd_type = nimsmrdata.infer_psd_type(e.psd)
    # hack to infer dwi, if caller doesn't know. (All dwi's at CNI use some variant of the epi2 psd.)
    if 'epi' in psd_type and 'epi2' in e.psd:
        is_dwi = True
    else:
        is_dwi = False
    e.scan_type = nimsmrdata.infer_scan_type(psd_type, e.num_timepoints, e.te, fov, mm_per_vox, is_dwi)
    print e.id, e.scan_type, e.fov
    transaction.commit()


