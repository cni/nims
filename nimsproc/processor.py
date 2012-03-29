#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

import os
import abc
import sys
import time
import shutil
import signal
import argparse
import tempfile
import threading

import dicom
import sqlalchemy
import transaction

import nimsutil
from nimsgears.model import *


class Processor(object):

    def __init__(self, db_uri, nims_path, physio_path, task, log, max_jobs, sleeptime):
        super(Processor, self).__init__()
        self.nims_path = nims_path
        self.physio_path = physio_path
        self.task = unicode(task) if task else None
        self.log = log
        self.max_jobs = max_jobs
        self.sleeptime = sleeptime

        self.alive = True
        init_model(sqlalchemy.create_engine(db_uri))
        self.reset_all()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            if threading.active_count()-1 < self.max_jobs:
                Job_A = sqlalchemy.orm.aliased(Job)
                subquery = sqlalchemy.exists().where(Job_A.data_container_id == DataContainer.id)
                subquery = subquery.where((Job_A.id < Job.id) & ((Job_A.status == u'new') | (Job_A.status == u'active')))
                query = Job.query.join(DataContainer).filter(Job.status==u'new')
                if self.task:
                    query = query.filter(Job.task==self.task)
                job = query.filter(~subquery).order_by(Job.id).first()

                if job:
                    if isinstance(job.data_container, Epoch):
                        pri_ds = job.data_container.primary_dataset
                        if isinstance(pri_ds, DicomData):
                            pipeline_class = DicomPipeline
                        elif isinstance(pri_ds, GEPfile):
                            pipeline_class = PfilePipeline

                    pipeline = pipeline_class(job, self.nims_path, self.physio_path, self.log)
                    job.status = u'active'      # make sure that this job is not picked up again in the next iteration
                    transaction.commit()
                    pipeline.start()
                else:
                    self.log.debug('Waiting for work...')
                    time.sleep(self.sleeptime)
            else:
                self.log.debug('Waiting for jobs to finish...')
                time.sleep(self.sleeptime)

    def reset_all(self):
        """Reset all active jobs to new."""
        query = Job.query.filter_by(status=u'active')
        if self.task:
            query = query.filter(Job.task==self.task)
        jobs = query.all()
        for job in jobs:
            self.log.info(u'Resetting job %s' % job)
            job.status = u'new'
        transaction.commit()


class Pipeline(threading.Thread):

    __metaclass__ = abc.ABCMeta

    def __init__(self, job, nims_path, physio_path, log):
        super(Pipeline, self).__init__()
        self.job = job
        self.nims_path = nims_path
        self.physio_path = physio_path
        self.log = log

    def run(self):
        DBSession.add(self.job)
        self.log.info(u'Processing %s' % self.job)
        if self.job.task == u'find':
            success = self.find()
        else:   # self.job.task == u'proc'
            success = self.process()
        if success:
            self.job.status = u'done'
            self.log.info(u'Processed  %s' % self.job)
        else:
            self.job.status = u'failed'
            self.log.info(u'Failed     %s' % self.job)
        transaction.commit()

    @abc.abstractmethod
    def find():
        # FIXME: wipe out all secondary datasets on the job's data_container
        return True

    @abc.abstractmethod
    def process():
        # FIXME: wipe out all derived datasets on the job's data_container
        return True


class DicomPipeline(Pipeline):

    def find(self):
        pri_ds = self.job.data_container.primary_dataset
        if pri_ds.physio_flag:
            physio_files = nimsutil.find_ge_physio(self.physio_path, pri_ds.timestamp, pri_ds.psd.encode('utf-8'))
            if physio_files:
                self.log.info('Found physio files: %s' % ', '.join([os.path.basename(pf) for pf in physio_files]))
                dataset = Dataset.at_path_for_file_and_type(self.nims_path, None, u'physio')
                dataset.file_cnt_tgt = len(physio_files)
                for f in physio_files:
                    shutil.copy2(f, os.path.join(self.nims_path, dataset.relpath))
                    dataset.file_cnt_act += 1
        transaction.commit()
        DBSession.add(self.job)
        return True

    def process(self):
        pri_ds = self.job.data_container.primary_dataset
        dcm_dir = os.path.join(self.nims_path, pri_ds.relpath)

        with nimsutil.TempDirectory() as tmpdir:
            outputdir = nimsutil.make_joined_path(tmpdir, 'outputdir')
            outbase = os.path.join(outputdir, pri_ds.container.name)
            nimsutil.dcm_convert(dcm_dir, outbase, self.log)

            if os.listdir(outputdir):
                self.log.info('Dicom files converted to %s' % os.listdir(outputdir))
                dataset = Dataset.at_path_for_file_and_type(self.nims_path, None, u'nifti')
                dataset.file_cnt_tgt = len(os.listdir(outputdir))
                for f in os.listdir(outputdir):
                    shutil.copy2(os.path.join(outputdir, f), os.path.join(self.nims_path, dataset.relpath))
                    dataset.file_cnt_act += 1

        transaction.commit()
        DBSession.add(self.job)
        return True


class PfilePipeline(Pipeline):

    def find(self):
        import random
        time.sleep(5 * random.random())
        return True

    def process(self):
        import random
        time.sleep(5 * random.random())
        return True


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', help='database URI')
        self.add_argument('nims_path', help='data location')
        self.add_argument('physio_path', help='path to physio data')
        self.add_argument('task', nargs='?', help='find|proc  (default is all)')
        self.add_argument('-j', '--jobs', type=int, default=1, help='maximum number of concurrent threads')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep between db queries')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)

    processor = Processor(args.db_uri, args.nims_path, args.physio_path, args.task, log, args.jobs, args.sleeptime)

    def term_handler(signum, stack):
        processor.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    processor.run()
    log.warning('Process halted')
