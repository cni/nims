#!/usr/bin/env python
#
# @author:  Sara Benito

import nimsutil
from nimsgears.model import *

import sys
import time
import signal
import argparse
import sqlalchemy
import transaction
import subprocess
import shutil
import os.path
import logging

# PROCESSOR_CMD = 'matlab file.m'
PROCESSOR_CMD = '/Users/sbenito/test_wh.sh'

log = logging.getLogger('processor-wh')

class ProcessorWH(object):

    def __init__(self, db_uri, nims_path, task, filters, reset, sleeptime, tempdir):
        self.nims_path = nims_path
        self.task = unicode(task) if task else None
        self.filters = filters
        self.sleeptime = sleeptime
        self.tempdir = tempdir
        self.alive = True
        init_model(sqlalchemy.create_engine(db_uri))

        if reset: self.reset_all()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            job = Job.query.join(DataContainer).join(Epoch) \
                .filter(Job.status==u'wh-pending').order_by(Job.id).with_lockmode('update').first()

            if not job:
                time.sleep(self.sleeptime)
                continue

            epoch = job.data_container
            session = Session.query.get(epoch.session_datacontainer_id)

            jobs = Job.query.join(DataContainer).join(Epoch) \
                     .filter(Epoch.session_datacontainer_id==session.id).with_lockmode('update').all()

            print 'Associated jobs:', jobs
            niftis = []
            datasets = []

            # make sure all epochs have been processed (niftis exist)
            for j in jobs:
                epoch = j.data_container
                assert isinstance(epoch, Epoch)

                niftis += [ds.primary_file_relpath for ds in epoch.datasets if ds.filetype == 'nifti']
                j.status = u'wh-process'

            if len(jobs) != len(niftis):
                # There is one or more Epochs missing niftis
                continue


            # Run the script
            print 'Processing niftis:', niftis
            # We need to create a temp dir to pass on the process command
            with nimsutil.TempDir() as tmp_in_dir, nimsutil.TempDir() as tmp_out_dir:
                print 'Input dir:', tmp_in_dir
                for nifti in niftis:
                    nifti_path = os.path.join(self.nims_path, nifti)
                    link_path = os.path.join(tmp_in_dir, nifti.split('/')[-1])
                    os.symlink(nifti_path, link_path)

                print 'Out dir:', tmp_out_dir

                res = subprocess.call( [PROCESSOR_CMD, tmp_in_dir, tmp_out_dir] )
                if res != 0:
                    log.error('Error running WH processor')
                    # Mark the processing as failed
                    for j in jobs:
                        j.status = u'failed'
                        j.activity = 'Failed to run WH matlab processsing'

                    transaction.commit()
                    return

                # Insert new dataset into the session
                dataset = Dataset.at_path(self.nims_path, u'png-figure')
                dataset.container = session
                # Copy output files into dataset.relpath

                log.info('Moving output files into ' + dataset.relpath)
                out_files = []
                for file in os.listdir(tmp_out_dir):
                    shutil.move(os.path.join(tmp_out_dir, file),
                                os.path.join(self.nims_path, dataset.relpath) )
                    out_files.append(file)

                print 'Out Files:', out_files
                dataset.filenames = set(dataset.filenames + out_files)
                dataset.updatetime = datetime.datetime.now()
                dataset.untrash()

                # Mark all the wh-pending jobs as done
                for j in jobs:
                    j.status = u'done'
                    j.activity = 'done'

                transaction.commit()


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', metavar='URI', help='database URI')
        self.add_argument('nims_path', metavar='DATA_PATH', help='data location')
        self.add_argument('-T', '--task', help='find|proc  (default is all)')
        self.add_argument('-e', '--filter', default=[], action='append', help='sqlalchemy filter expression')
        # self.add_argument('-j', '--jobs', type=int, default=1, help='maximum number of concurrent threads')
        # self.add_argument('-k', '--reconjobs', type=int, default=8, help='maximum number of concurrent recon jobs')
        self.add_argument('-r', '--reset', action='store_true', help='reset currently active (crashed) jobs')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep between db queries')
        self.add_argument('-t', '--tempdir', help='directory to use for temporary files')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='log level (default: info)')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')


if __name__ == '__main__':
    # workaround for http://bugs.python.org/issue7980
    import datetime # used in nimsutil
    datetime.datetime.strptime('0', '%S')

    args = ArgumentParser().parse_args()
    nimsutil.configure_log(args.logfile, not args.quiet, args.loglevel)
    processor = ProcessorWH(args.db_uri, args.nims_path, args.task,
                        args.filter, args.reset, args.sleeptime, args.tempdir)

    def term_handler(signum, stack):
        processor.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    processor.run()
    log.warning('Process halted')

