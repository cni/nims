#!/usr/bin/env python
#
# @author:  Robert Dougherty

import transaction
import sqlalchemy
from nimsgears.model import *
from os.path import basename,exists,join
from shutil import copy
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
    arg_parser.add_argument('-d', '--dataset_id', type=int, default=None, help='dataset id of the target location')
    arg_parser.add_argument('-f', '--force', action='store_true', help='Force overwrite of existing files with the same name')
    arg_parser.add_argument('files', nargs='+', help='files to add')
    args = arg_parser.parse_args()

    init_model(sqlalchemy.create_engine(args.uri))

    ds = Dataset.get(args.dataset_id)

    ds_path = join(args.nims_path, ds.relpath)

    # ensure all the input files exist and that names don't conflict
    err = True
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



