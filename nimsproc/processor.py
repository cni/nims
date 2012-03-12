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
from nimsutil import dicomutil
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
                query = Job.query.filter(Job.status==u'new')
                if self.task:
                    query = query.filter(Job.task==self.task)
                jobs = query.order_by(Job.id).limit(100).all()
                for job in jobs:
                    query = Job.query.filter(Job.data_container==job.data_container)
                    older_job = query.filter(Job.id<job.id).filter((Job.status==u'new') | (Job.status==u'active')).first()
                    if older_job:
                        job = None
                        continue
                    break
                else:
                    job = None
                if job and (job.task == self.task or self.task is None):
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

    TYPE_ORIGINAL = ['ORIGINAL', 'PRIMARY', 'OTHER']
    TYPE_EPI =      ['ORIGINAL', 'PRIMARY', 'EPI', 'NONE']
    TYPE_SCREEN =   ['DERIVED', 'SECONDARY', 'SCREEN SAVE']
    TAG_DIFFUSION_DIRS = (0x0019, 0x10e0)

    def find(self):
        pri_ds = self.job.data_container.primary_dataset
        if pri_ds.physio_flag:
            physio_files = nimsutil.find_ge_physio(self.physio_path, pri_ds.timestamp, pri_ds.psd.encode('utf-8'))
            if physio_files:
                self.log.info('Found physio files: %s' % str(physio_files))
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
        dcm_list = sorted([dicom.read_file(os.path.join(dcm_dir, f)) for f in os.listdir(dcm_dir)], key=lambda dcm: dcm.InstanceNumber)
        header = dcm_list[0]

        try:
            image_type = header.ImageType
        except:
            return False

        with nimsutil.TempDirectory() as tmpdir:
            outputdir = nimsutil.make_joined_path(tmpdir, 'outputdir')
            outbase = os.path.join(outputdir, pri_ds.container.name)

            if image_type == self.TYPE_SCREEN:
                dicomutil.dcm_to_img(dcm_list, outbase)
            if image_type == self.TYPE_ORIGINAL and self.TAG_DIFFUSION_DIRS in header and header[self.TAG_DIFFUSION_DIRS].value > 0:
                dicomutil.dcm_to_dti(dcm_list, outbase)
            if image_type == self.TYPE_ORIGINAL or header.ImageType == self.TYPE_EPI:
                try: # FIXME: this try/except should not be here; bandaid since dicomutil.dcm_to_nii fails for single slice
                    dicomutil.dcm_to_nii(dcm_list, outbase)
                except ValueError:
                    pass

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
