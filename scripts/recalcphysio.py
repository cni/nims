#!/usr/bin/env python
#
# @author:  Robert Dougherty

import os
import transaction
import nimsutil
from nimsgears.model import *

data_path = '/nimsfs/nims'

peripheral_datasets = Dataset.query.filter(Dataset.kind==u'peripheral' and Dataset.filetype==u'physio').all()
pd_ids = [p.id for p in peripheral_datasets]

for pid in pd_ids:
    p = Dataset.query.filter(Dataset.id==pid).first()
    phys_filename = [f for f in p.filenames if f.endswith('_physio.tgz')]
    if len(phys_filename) == 1:
        print('%s: recomputing regressors...' % p.container)
        physio_file = os.path.join(data_path, p.relpath, phys_filename[0])
        dc = p.container
        phys = nimsutil.physio.PhysioData(physio_file, dc.tr, dc.num_timepoints, dc.num_slices/dc.num_bands)
        # Get rid of old regressor and rawdata files
        for reg_file in [f for f in p.filenames if 'regressors' in f or 'rawdata' in f]:
            os.remove(os.path.join(data_path, p.relpath, reg_file))
        basename = os.path.join(data_path, p.relpath, '%s_physio_' % dc.name)
        try:
            phys.write_regressors(basename + 'regressors.csv.gz')
            phys.write_raw_data(basename + 'rawdata.json.gz')
        except nimsutil.physio.PhysioDataError:
            print('error generating regressors from physio data')
        p.filenames = os.listdir(os.path.join(data_path, p.relpath))
        transaction.commit()
    else:
        print('%s: no unique physio file found: %s.' % (p.container, p.filenames))


