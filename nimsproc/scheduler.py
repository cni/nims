#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import time
import shutil
import signal
import tarfile
import argparse
import datetime

import sqlalchemy
import transaction

import nimsutil
from nimsgears.model import *


class Scheduler(object):

    def __init__(self, db_uri, nims_path, log, sleeptime, cooltime):
        super(Scheduler, self).__init__()
        self.nims_path = nims_path
        self.log = log
        self.sleeptime = sleeptime
        self.cooltime = datetime.timedelta(seconds=cooltime)

        self.alive = True
        init_model(sqlalchemy.create_engine(db_uri))
        self.reset_all()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            # relaunch jobs that need rerun
            for job in Job.query.filter((Job.status != u'running') & (Job.status != u'abandoned') & (Job.needs_rerun == True)).all():
                job.status = u'pending'
                job.activity = u'reset to pending'
                self.log.info(u'Reset       %s to pending' % job)
                job.needs_rerun = False
            transaction.commit()

            # deal with dirty data containers
            dc = (DataContainer.query
                    .filter(DataContainer.dirty == True)
                    .filter(~DataContainer.datasets.any(Dataset.updatetime > (datetime.datetime.now() - self.cooltime)))
                    .order_by(DataContainer.timestamp).first())
            if dc:
                dc.dirty = False
                dc.scheduling = True
                transaction.commit()
                DBSession.add(dc)

                # compress data if needed
                for ds in [ds for ds in dc.original_datasets if not ds.compressed]:
                    self.log.info(u'Compressing %s %s' % (dc, ds.filetype))
                    dataset_path = os.path.join(self.nims_path, ds.relpath)
                    if ds.filetype == nimsutil.dicomutil.DicomAcquisition.filetype:
                        arcdir = '%d_%d_%d_dicoms' % (dc.session.exam, dc.series, dc.acq)
                        arcdir_path = os.path.join(dataset_path, arcdir)
                        os.mkdir(arcdir_path)
                        for filename in [f for f in os.listdir(dataset_path) if not f.startswith(arcdir)]:
                            os.rename(os.path.join(dataset_path, filename), os.path.join(arcdir_path, filename))
                        with tarfile.open('%s.tgz' % arcdir_path, 'w:gz', compresslevel=6) as archive:
                            archive.add(arcdir_path, arcname=os.path.basename(arcdir_path))
                        shutil.rmtree(arcdir_path)
                        ds.filenames = os.listdir(dataset_path)
                        ds.compressed = True
                        transaction.commit()
                    elif ds.filetype == nimsutil.pfile.PFile.filetype:
                        for pfilepath in [os.path.join(dataset_path, f) for f in os.listdir(dataset_path) if not f.startswith('_')]:
                            nimsutil.gzip_inplace(pfilepath, 0o644)
                        ds.filenames = os.listdir(dataset_path)
                        ds.compressed = True
                        transaction.commit()
                    DBSession.add(dc)

                # schedule job
                self.log.info(u'Inspecting  %s' % dc)
                new_digest = nimsutil.redigest(os.path.join(self.nims_path, dc.primary_dataset.relpath))
                if dc.primary_dataset.digest != new_digest:
                    dc.primary_dataset.digest = new_digest
                    job = Job.query.filter_by(data_container=dc).filter_by(task=u'find&proc').first()
                    if not job:
                        job = Job(data_container=dc, task=u'find&proc', status=u'pending', activity=u'pending')
                        self.log.info(u'Created job %s' % job)
                    elif job.status != u'pending' and not job.needs_rerun:
                        job.needs_rerun = True
                        self.log.info(u'Marked job  %s for restart' % job)
                dc.scheduling = False
                self.log.info(u'Done        %s' % dc)
                transaction.commit()
            else:
                time.sleep(self.sleeptime)

    def reset_all(self):
        """Reset all scheduling data containers to dirty."""
        for dc in DataContainer.query.filter_by(scheduling=True).all():
            dc.dirty = True
            dc.scheduling = False
            self.log.info('Reset data container %s to dirty' % dc)
        transaction.commit()


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', help='database URI')
        self.add_argument('nims_path', help='data location')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep between db queries')
        self.add_argument('-c', '--cooltime', type=int, default=30, help='time to let data cool before processing')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    log = nimsutil.get_logger(args.logname, args.logfile, not args.quiet, args.loglevel)
    scheduler = Scheduler(args.db_uri, args.nims_path, log, args.sleeptime, args.cooltime)

    def term_handler(signum, stack):
        scheduler.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    scheduler.run()
    log.warning('Process halted')
