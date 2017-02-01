#!/usr/bin/env python
#
# @author:  Robert Dougherty


import transaction
import sqlalchemy
from nimsgears.model import *

from shutil import move
from os import path
from glob import glob


nims_path = '/net/cnifs/cnifs/nims'
init_model(sqlalchemy.create_engine('postgresql://nims:nims@cnifs.stanford.edu:5432/nims'))

exam = 13041

epochs = Epoch.query.join(Session, Epoch.session).filter(Session.exam==exam).all()
datasets = [d.id for e in epochs for d in e.datasets if d.label==u'nifti_ssg']

for d_id in datasets:
    d = Dataset.get(d_id)
    files = glob(path.join(nims_path, d.relpath, '*'))
    file_names = [path.basename(f) for f in files]
    new_names = [f.split('.')[0] + '_ssg.' + '.'.join(f.split('.')[1:]) for f in file_names]
    new_files = [path.join(nims_path, d.relpath, f) for f in new_names]
    d.filenames = [f.decode() for f in new_names]
    transaction.commit()
    for old_file,new_file in zip(files,new_files):
        move(old_file, new_file)

