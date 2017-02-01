#!/usr/bin/env python
#
# @author:  Robert Dougherty

import transaction
import sqlalchemy
from nimsgears.model import *
from os.path import basename,exists,join
from shutil import copy2 as copy
from glob import glob

if __name__ == '__main__':
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.description  = ('Add files to the NIMS database. Note that this must be run one a machine\n'
                               'and as a user that have write-access to the NIMS file store.\n')
    uri = 'postgresql://nims:nims@cnifs.stanford.edu:5432/nims'
    nims_path = '/net/cnifs/cnifs/nims'
    arg_parser.add_argument('-p', '--nims_path', metavar='DATA_PATH', default=nims_path, help='NIMS data location (must be writable; default:%s)' % nims_path)
    arg_parser.add_argument('-u', '--uri', metavar='URI', default=uri, help='URI pointing to the NIMS database. (Default=%s)' % uri)
    arg_parser.add_argument('-d', '--dataset_id', type=int, default=None, help='dataset id of the target location (dataset must exist!)')
    arg_parser.add_argument('-e', '--epoch_id', type=int, default=None, help='epoch id of the epoch this dataset should attach to (the dataset will be created)')
    arg_parser.add_argument('-f', '--force', action='store_true', help='Force overwrite of existing files with the same name')
    arg_parser.add_argument('-t', '--type', default = 'nifti', help='Data type for new datasets (nifti, physio, pfile, dicom, img_pyr, etc.-- default is nifti)')
    arg_parser.add_argument('-l', '--label', help='NIMS GUI label for new datasets (defaults to the above type if not set; e.g., "nifti" for a nifti type)')
    arg_parser.add_argument('-x', '--exam', help='Exam number (alternative to specifying an epoch_id-- set exam, series, acquisition)')
    arg_parser.add_argument('-s', '--series', help='Series number')
    arg_parser.add_argument('-a', '--acq', help='Acquisition number')
    arg_parser.add_argument('files', nargs='+', help='files to add')
    args = arg_parser.parse_args()

    init_model(sqlalchemy.create_engine(args.uri))

    err = True

    if args.dataset_id!=None:
        ds = Dataset.get(args.dataset_id)
        ds_path = join(args.nims_path, ds.relpath)
        # ensure all the input files exist and that names don't conflict
        for f in args.files:
            if not exists(f):
                print('ERROR: input file %s does not seem to exist. Nothing will be added.' % f)
            elif basename(f) in ds.filenames:
                if args.force:
                    print('WARNING: input file %s has the same name as an existing file (%s).' % (f,', '.join(ds.filenames)))
                    resp = raw_input('Are you sure you want to overwrite it? (y/n) ')
                    if len(resp)>0 and resp[0]=='y':
                        err = False
                        print('Overwriting %s with %s.' % (f,', '.join(ds.filenames)))
                    else:
                        print('Aborting.')
                else:
                    print('ERROR: input file %s has the same name as an existing file (%s). Nothing will be added. Try --force to force overwrite.' % (f,', '.join(ds.filenames)))
            else:
                err = False
        if not err:
            for f in args.files:
                ds = Dataset.get(args.dataset_id)
                copy(f, ds_path)
            ds.filenames = [basename(f).decode() for f in glob(join(ds_path,'*'))]
            transaction.commit()
            ds = Dataset.get(args.dataset_id)
            print('File(s) in db: %s' % ', '.join(ds.filenames))
            print('File(s) on disk: %s' % ', '.join([basename(f) for f in glob(join(ds_path,'*'))]))
    elif args.epoch_id!=None or (args.exam!=None and args.series!=None and args.acq!=None):
        # create a new dataset
        if args.epoch_id!=None:
            epoch = Epoch.get(args.epoch_id)
        else:
            epoch = Epoch.query.join(Session, Epoch.session).filter(Session.exam==args.exam, Epoch.series==args.series, Epoch.acq==args.acq).first()

        if epoch:
            if args.label:
                ds = Dataset.at_path(args.nims_path, args.type.decode(), label=args.label.decode())
            else:
                ds = Dataset.at_path(args.nims_path, args.type.decode())

            ds_id = ds.id
            ds_path = join(args.nims_path, ds.relpath)
            print('Created dataset id %d' % ds_id)
            ds.kind = u'derived'
            ds.container = epoch
            # May want to update epoch metadata?
            #ds.container.size = pf.size
            #ds.container.mm_per_vox = pf.mm_per_vox
            #ds.container.num_slices = pf.num_slices
            #ds.container.num_timepoints = pf.num_timepoints
            #ds.container.duration = datetime.timedelta(seconds=pf.duration)
            filenames = []
            for f in args.files:
                if not exists(f):
                    print('ERROR: input file %s does not seem to exist. Nothing will be added.' % f)
                else:
                    filenames.append(f)
                    copy(f, ds_path)
            ds.filenames = [basename(f).decode() for f in glob(join(ds_path,'*'))]
            transaction.commit()
            ds = Dataset.get(ds_id)
            print('File(s) in db: %s' % ', '.join(ds.filenames))
            print('File(s) on disk: %s' % ', '.join([basename(f) for f in glob(join(ds_path,'*'))]))
        else:
            print('ERROR: epoch not found. Nothing added.')



