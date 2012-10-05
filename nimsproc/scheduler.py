#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import time
import shutil
import signal
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
            dc = (DataContainer.query
                    .filter(DataContainer.dirty == True)
                    .filter(~DataContainer.datasets.any(Dataset.updatetime > (datetime.datetime.now() - self.cooltime)))
                    .first())
            if dc:
                dc.dirty = False
                dc.scheduling = True
                transaction.commit()
                DBSession.add(dc)

                self.log.info(u'Inspecting  %s' % dc)
                if dc.primary_dataset.redigest(self.nims_path):
                    if not Job.query.filter_by(data_container=dc).filter_by(task=u'proc').filter((Job.status == u'waiting') | (Job.status == u'pending')).first():
                        proc_job = Job(data_container=dc, task=u'proc', status=u'waiting', activity=u'waiting', nims_path=self.nims_path)
                        self.log.info(u'Created job %s' % proc_job)
                        transaction.commit()
                        DBSession.add(dc)
                    if not Job.query.filter_by(data_container=dc).filter_by(task=u'find').filter((Job.status == u'waiting') | (Job.status == u'pending')).first():
                        proc_job = Job.query.filter_by(data_container=dc).filter_by(task=u'proc').order_by(-Job.id).first()
                        find_job = Job(data_container=dc, task=u'find', status=u'pending', activity=u'pending', next_job_id=proc_job.id, nims_path=self.nims_path)
                        self.log.info(u'Created job %s' % find_job)
                        transaction.commit()
                        DBSession.add(dc)
                dc.scheduling = False
                transaction.commit()
            else:
                time.sleep(self.sleeptime)

    def reset_all(self):
        """Reset all scheduling data containers to dirty."""
        for dc in DataContainer.query.filter_by(scheduling=True).all():
            dc.dirty = True
            dc.scheduling = False
        transaction.commit()
        self.log.info('Reset "scheduling" data containers to dirty')


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


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)

    scheduler = Scheduler(args.db_uri, args.nims_path, log, args.sleeptime, args.cooltime)

    def term_handler(signum, stack):
        scheduler.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    scheduler.run()
    log.warning('Process halted')
