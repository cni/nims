#!/usr/bin/env python

import numpy as np
import nibabel as nb
import transaction
import sqlalchemy
from nimsgears.model import *
import os

def fix_coil_combined_image(nifti_fname):
    ni = nb.load(nifti_fname)
    data = ni.get_data().astype(float)
    data[...,-1] = np.round(np.sqrt(np.sum(data[...,:-1]**2, axis=3))).astype(np.int16)

    ni_new = nb.Nifti1Image(data, None, header=ni.get_header())
    ni_new.update_header()
    return ni_new

def rerecon(epoch_id, nimspath):
    epoch = Epoch.get(epoch_id)
    ds = [ds for ds in epoch.datasets if ds.filetype==u'nifti']
    print('Processing %s from exam %d...' % (epoch.description, epoch.session.exam))
    if len(ds)==1 and len(ds[0].filenames)==1:
        fn = os.path.join(nimspath, ds[0].relpath, ds[0].filenames[0])
        ni = fix_coil_combined_image(fn)
        nb.save(ni, fn)

if __name__ == "__main__":
    import argparse
    import os
    import sys

    arg_parser = argparse.ArgumentParser()
    arg_parser.description = """Fix coil-combined image in nims."""
    arg_parser.add_argument('-d', '--db_uri', default='postgresql://nims:nims@cnifs.stanford.edu:5432/nims', help='NIMS database URI')
    arg_parser.add_argument('-n', '--nims_path', default='/net/cnifs/cnifs/nims', help='NIMS data location (must be writable)')
    arg_parser.add_argument('-s', '--session_id', type=int, help='To run recon on all epochs in a session, pass the session id (here) or exam # (below).')
    arg_parser.add_argument('-x', '--exam_num', type=int, help='To run recon on all epochs in a session, pass the exam # (here) or session id (above).')
    arg_parser.add_argument('-e', '--epoch_id', type=int, help='Run recon on just this epoch.')
    arg_parser.add_argument('-p', '--exp_id', type=int, help='Run recon on all epochs in this experiment.')
    arg_parser.add_argument('-m', '--match', default='', help='String to match in series description.')
    args = arg_parser.parse_args()

    init_model(sqlalchemy.create_engine(args.db_uri))
    if args.epoch_id:
        epochs = [args.epoch_id]
        rerecon(args.epoch_id, args.nims_path)
    elif args.session_id or args.exam_num:
        if args.session_id:
            s = Session.get(args.session_id)
        else:
            s = Session.query.filter(Session.exam==args.exam_num).first()
        epoch_ids = [e.id for e in s.epochs if args.match in e.description]
        for eid in epoch_ids:
            try:
                rerecon(eid, args.nims_path)
            except:
                print('%d failed.' % eid)
    elif args.exp_id:
        epoch_ids = [e.id for e in Epoch.query.join(Session,Epoch.session).join(Subject,Session.subject).join(Experiment,Subject.experiment)
.filter(Experiment.id==args.exp_id).all() if args.match in e.description]
        for eid in epoch_ids:
            try:
                rerecon(eid, args.nims_path)
            except:
                print('%d failed.' % eid)


