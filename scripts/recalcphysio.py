#!/usr/bin/env python
#
# @author:  Robert Dougherty

import os
import transaction
import sqlalchemy
from nimsgears.model import *
import time
import shutil
import nimsdata

# Will recompute all the qa on a specified experiment (by exp_id)
exp_id = 64730

data_path = '/net/cnifs/cnifs/nims'
tmpdir = '/tmp/physio%d' % int(time.time())
os.mkdir(tmpdir)
db_uri = 'postgresql://nims:nims@cnifs.stanford.edu:5432/nims'

init_model(sqlalchemy.create_engine(db_uri))

sessions = Session.query.join(Subject,Session.subject).join(Experiment,Subject.experiment).filter(Experiment.id==exp_id).all()
sid = [s.id for s in sessions]
exams = [Session.get(s).exam for s in sid]
#exams = [4797, 4831, 4838, 4839]

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
        ds = dc.primary_dataset
        phys = nimsdata.nimsphysio.NIMSPhysio(physio_file, dc.tr, dc.num_timepoints)
        ni = nimsdata.parse(os.path.join(data_path, ds.primary_file_relpath))
        phys.slice_order = ni.get_slice_order()
        cur_files = os.listdir(os.path.join(data_path, p.relpath))
        # Get rid of old regressor and rawdata files
        for reg_file in [f for f in cur_files if 'regressors' in f or 'rawdata' in f]:
            shutil.move(os.path.join(data_path, p.relpath, reg_file), tmpdir)
        basename = os.path.join(data_path, p.relpath, '%s_physio_' % dc.name)
        try:
            phys.write_regressors(basename + 'regressors.csv.gz')
            #phys.write_raw_data(basename + 'rawdata.json.gz')
        except nimsdata.nimsphysio.NIMSPhysioError:
            print('error generating regressors from physio data')
        p.filenames = os.listdir(os.path.join(data_path, p.relpath))
        transaction.commit()
    else:
        print('%s: no unique physio file found: %s.' % (p.container, p.filenames))


