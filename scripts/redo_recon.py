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

def rerecon(epoch_id, nimspath, njobs=8):
    # Note: the caller may have locked the db, so we should be sure to commit the transaction asap.
    start_secs = time.time()
    epoch = Epoch.get(epoch_id)
    if force or epoch.qa_status==u'pending' or epoch.qa_status==u'rerun':
        epoch.qa_status = u'running'
        transaction.commit()
        DBSession.add(epoch)
    else:
        if epoch.qa_status==u'running':
            print('%s epoch id %d (%s) QA: appears to be running; aborting.' % (time.asctime(), epoch_id, str(epoch)))
        else:
            print('%s epoch id %d (%s) QA: appears to be done already; aborting. Use "--force" to redo it.' % (time.asctime(), epoch_id, str(epoch)))
        transaction.commit()
        return


if __name__ == "__main__":
    import argparse
    import os
    import sys

    arg_parser = argparse.ArgumentParser()
    arg_parser.description = """Redo a recon in NIMS."""
    arg_parser.add_argument('-d', '--db_uri', default='postgresql://nims:nims@cnifs.stanford.edu:5432/nims', help='NIMS database URI')
    arg_parser.add_argument('-p', '--nims_path', default='/net/cnifs/cnifs/nims', help='NIMS data location (must be writable)')
    arg_parser.add_argument('-s', '--session_id', type=int, help='To run recon on all epochs in a session, pass the session id (here) or exam # (below).')
    arg_parser.add_argument('-x', '--exam_num', type=int, help='To run recon on all epochs in a session, pass the exam # (here) or session id (above).')
    arg_parser.add_argument('-e', '--epoch_id', type=int, help='Run recon on just this epoch.')
    arg_parser.add_argument('-j', '--jobs', type=int, default=8, metavar='[8]', help='Number of jobs to run in parallel.')
    args = arg_parser.parse_args()

    init_model(sqlalchemy.create_engine(args.db_uri))
    if args.epoch_id:
        epochs = [args.epoch_id]
        rerecon(args.epoch_id, args.nims_path, njobs=args.jobs)
    elif args.session_id or args.exam_num:
        if args.session_id:
            s = Session.get(args.session_id)
        else:
            s = Session.query.filter(Session.exam==args.exam_num).first()
        epoch_ids = [e.id for e in s.epochs if e.scan_type==scan_type]
        for eid in epoch_ids:
            rerecon(eid, args.nims_path, njobs=args.jobs)


