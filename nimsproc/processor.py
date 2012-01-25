# @author:  Reno Bowen
#           Gunnar Schaefer

import os
import abc
import sys
import time
import shutil
import argparse
import tempfile
import threading

import sqlalchemy
import transaction

import nimsutil
from nimsgears import model


class Processor(object):

    def __init__(self, db_uri, nims_path, workerclass, log, sleeptime, **kwargs):
        super(Processor, self).__init__()
        self.nims_path = nims_path
        self.workerclass = workerclass
        self.log = log
        self.sleeptime = sleeptime
        self.kwargs = kwargs

        self.alive = True
        model.init_model(sqlalchemy.create_engine(db_uri))
        self.reset_all()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            query = model.Job.query
            query = query.filter_by(task=self.workerclass.taskname)
            query = query.filter(model.Job.max_workers > threading.active_count()-1)
            job = query.filter_by(status=u'new').first()
            if job:
                worker = self.workerclass(job, self.nims_path, self.log, **self.kwargs)
                job.status = u'active'
                transaction.commit()
                worker.start()
            else:
                transaction.abort()
                self.log.debug('Waiting for work...')
                time.sleep(self.sleeptime)

    def reset_all(self):
        """Reset all active jobs to new."""
        for job in model.Job.query.filter_by(task=self.workerclass.taskname).filter_by(status=u'active').all():
            print 'resetting job %s' % job
            job.status = u'new'
        transaction.commit()


class Worker(threading.Thread):

    __metaclass__ = abc.ABCMeta

    def __init__(self, job, nims_path, log, **kwargs):
        super(Worker, self).__init__()
        self.job = job
        self.nims_path = nims_path
        self.log = log
        self.kwargs = kwargs

    def run(self):
        model.DBSession.add(self.job)
        input_path = os.path.join(self.nims_path, self.job.dataset.path)
        self.log.info(u'Processing %s' % self.job)
        transaction.commit()

        with nimsutil.TempDirectory() as temp_dir:
            new_dataset, filenames = self.process(input_path, os.path.join(temp_dir, self.job.dataset.epoch.name), **self.kwargs)

            model.DBSession.add(self.job)
            if new_dataset:
                dest = os.path.join(self.nims_path, self.job.dataset.epoch.path)
                for f in filenames:
                    shutil.move(f, os.path.join(dest, os.path.basename(f)))
                new_dataset.epoch = self.job.dataset.epoch
                if new_dataset.tasks:
                    new_dataset.is_dirty = True
                self.job.status = u'done'
            else:
                self.job.status = u'failed'
        self.log.info(u'Processed  %s' % self.job)
        transaction.commit()

    @abc.abstractmethod
    def process(input_path, output_path):
        pass

    @abc.abstractproperty
    def result_datatype():
        return model.Dataset

    def result_dataset(self):
        ds = self.result_datatype.query.filter_by(epoch=self.job.dataset.epoch).first()
        if not ds:
            ds = self.result_datatype()
            ds.epoch = self.job.dataset.epoch
        return ds


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('db_uri', help='database URI')
        self.add_argument('nims_path', help='data location')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep between db queries')
        self.add_argument('-n', '--logname', default=__file__, help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')

    def error(self, message):
        self.print_help()
        sys.exit(1)
