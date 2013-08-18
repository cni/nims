#!/usr/bin/env python
#
# @author:  Robert Dougherty

import os
import transaction
import nimsutil
from nimsgears.model import *
import time
import shutil

data_path = '/nimsfs/nims'
tmpdir = '/tmp/physio%d' % int(time.time())
os.mkdir(tmpdir)

exams = [4797, 4831, 4838, 4839]

if not exams:
    # Get them all
    pd = Dataset.query.filter(Dataset.kind==u'peripheral').filter(Dataset.filetype==u'physio').all()
else:
    pd = []
    for exam in exams:
        cur_pd = (Dataset.query
                        .join(Epoch, Dataset.container)
                        .join(Session, Epoch.session)
                        .filter(Session.exam==exam)
                        .filter(Dataset.kind==u'peripheral')
                        .filter(Dataset.filetype==u'physio').all())

        pd += cur_pd

pd_ids = [p.id for p in pd]

for pid in pd_ids:
    p = Dataset.query.filter(Dataset.id==pid).first()
    phys_filename = [f for f in p.filenames if f.endswith('_physio.tgz')]
    if len(phys_filename) == 1:
        print('%s: recomputing regressors...' % p.container)
        physio_file = os.path.join(data_path, p.relpath, phys_filename[0])
        dc = p.container
        phys = nimsutil.physio.PhysioData(physio_file, dc.tr, dc.num_timepoints, dc.num_slices/dc.num_bands)
        # Get rid of old regressor and rawdata files
<<<<<<< Updated upstream
        cur_files = os.listdir(os.path.join(data_path, p.relpath))
        for reg_file in [f for f in cur_files if 'regressors' in f or 'rawdata' in f]:
            shutil.move(os.path.join(data_path, p.relpath, reg_file), tmpdir)
        basename = os.path.join(data_path, p.relpath, '%s_physio_' % dc.name)
        try:
            phys.write_regressors(basename + 'regressors.csv.gz')
            #phys.write_raw_data(basename + 'rawdata.json.gz')
        except nimsutil.physio.PhysioDataError:
            print('error generating regressors from physio data')
=======
        for reg_file in [f for f in p.filenames if 'regressors' in f or 'rawdata' in f]:
            os.remove(os.path.join(data_path, p.relpath, reg_file))
        #basename = os.path.join(data_path, p.relpath, '%s_physio_' % dc.name)
        #try:
        #    phys.write_regressors(basename + 'regressors.csv.gz')
        #    phys.write_raw_data(basename + 'rawdata.json.gz')
        #except nimsutil.physio.PhysioDataError:
        #    print('error generating regressors from physio data')
>>>>>>> Stashed changes
        p.filenames = os.listdir(os.path.join(data_path, p.relpath))
        transaction.commit()
    else:
        print('%s: no unique physio file found: %s.' % (p.container, p.filenames))


