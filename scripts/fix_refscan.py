#!/usr/bin/env python

import os
from subprocess import check_call
from shutil import rmtree
from glob import glob
import shlex
import transaction
import sqlalchemy
from nimsgears.model import *

nimspath = '/net/nimsfs/mnt/nimsfs/nims/'

# 190571 190578
# 192493 192496 192688 192690 193264 195958 195852 195854 195856 190726 190730

def fix_refscans(epochs):
    for eid in epochs:
        epoch = Epoch.get(eid)
        print('Fixing eid %d (%s)...' % (eid,str(epoch)))
        try:
            good_epochs = [e.id for e in epoch.session.epochs if e.id not in epochs and e.num_bands==epoch.num_bands and e.num_slices==epoch.num_slices and e.phase_encode_undersample==epoch.phase_encode_undersample and e.size_x==epoch.size_x and e.size_y==epoch.size_y]
            # and (('pe1' in e.description and 'pe1' in epoch.description) or ('pe1' not in e.description and 'pe1' not in epoch.description))]
            deltas = [abs((epoch.timestamp - Epoch.get(e).timestamp).total_seconds()) for e in good_epochs]
            good_epoch = Epoch.get(good_epochs[deltas.index(min(deltas))])
            bad_ds_id = [d.id for d in epoch.datasets if d.filetype==u'pfile'][0]
            good_ds_id = [d.id for d in good_epoch.datasets if d.filetype==u'pfile'][0]

            good_ds = Dataset.get(good_ds_id)
            bad_ds = Dataset.get(bad_ds_id)

            good_filepath = os.path.join(nimspath, good_ds.relpath, good_ds.filenames[0])
            cmd = 'tar --use-compress-program=pigz -xf ' + good_filepath
            print(cmd)
            check_call(shlex.split(cmd))
            good_dir = os.path.splitext(good_ds.filenames[0])[0]
            good_ref = glob(os.path.join(good_dir, 'P*_refscan.7'))
            if len(good_ref)<1:
                good_ref = glob(os.path.join(good_dir, 'P*_ref.dat'))
                if len(good_ref)<1:
                    print('  No refscan or ref.dat. Skipping.')
                    continue
                print('  No refscan file-- trying to use ref.dat...')
            good_ref = good_ref[0]

            bad_filepath = os.path.join(nimspath, bad_ds.relpath, bad_ds.filenames[0])
            cmd = 'tar --use-compress-program=pigz -xf ' + bad_filepath
            print(cmd)
            check_call(shlex.split(cmd))

            abort = True
            bad_dir = os.path.splitext(bad_ds.filenames[0])[0]
            pfile_name = os.path.basename(glob(os.path.join(bad_dir, 'P?????.7'))[0])
            bad_refscan = os.path.join(bad_dir, pfile_name+'_refscan.7')
            if os.path.exists(bad_refscan) or os.path.exists(os.path.join(bad_dir, pfile_name+'_ref.dat')):
                print('refscan or ref.dat exists in %s! Refusing to overwrite.' % bad_dir)
            else:
                cmd = 'cp ' + good_ref + ' ' + bad_refscan
                print(cmd)
                check_call(shlex.split(cmd))
                abort = False

            bad_vrgf = os.path.join(bad_dir, pfile_name+'_vrgf.dat')
            if not os.path.exists(bad_vrgf):
                print('  vrgf is missing! Trying to fix that...')
            good_vrgf = glob(os.path.join(good_dir, 'P*_vrgf.dat'))
            if len(good_vrgf)>0:
                cmd = 'cp ' + good_vrgf[0] + ' ' + bad_vrgf
                print(cmd)
                check_call(shlex.split(cmd))
                abort = False
            else:
                print('  no vrgf in the "good" dir!!!')

            if not abort:
                pfiles = glob(os.path.join(bad_dir, 'P*'))
                cmd = 'tar --use-compress-program=pigz -cf ' + bad_dir + '.tgz ' + bad_dir + '/METADATA.json ' + bad_dir + '/DIGEST.txt ' + ' '.join(pfiles)
                print(cmd)
                check_call(shlex.split(cmd))
                cmd = 'mv ' + bad_dir + '.tgz ' + bad_filepath
                print(cmd)
                check_call(shlex.split(cmd))
                rmtree(good_dir)
                # Just in case there's an error and we clobber the archive, keep this around
                rmtree(bad_dir)
        except:
            print('FAILED to fix eid %d (%s)...' % (eid,str(epoch)))

if __name__ == '__main__':
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.description  = ('Fix missing refsacn problem for mux data. Note that this must be run on a machine\n'
                               'and as a user that have write-access to the NIMS file store.\n')
    uri = 'postgresql://nims:nims@cni.stanford.edu:5432/nims'
    arg_parser.add_argument('-p', '--nimspath', metavar='DATA_PATH', default=nimspath, help='NIMS data location (must be writable; default:%s)' % nimspath)
    arg_parser.add_argument('-u', '--uri', metavar='URI', default=uri, help='URI pointing to the NIMS database. (Default=%s)' % uri)
    arg_parser.add_argument('epoch_ids', type=int, nargs='+', help='List of epoch ids to be fixed')
    args = arg_parser.parse_args()

    init_model(sqlalchemy.create_engine(args.uri))

    fix_refscans(args.epoch_ids)


