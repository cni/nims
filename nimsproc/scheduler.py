#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import time
import signal
import argparse
import datetime

import sqlalchemy
import transaction

import nimsutil
from nimsgears.model import *


class Scheduler(object):

    def __init__(self, db_uri, log, sleeptime, cooltime):
        super(Scheduler, self).__init__()
        self.log = log
        self.sleeptime = sleeptime
        self.cooltime = datetime.timedelta(seconds=cooltime)
        self.alive = True
        init_model(sqlalchemy.create_engine(db_uri))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            query = DataContainer.query.join(Dataset)
            query = query.filter((DataContainer.needs_finding==True) | (DataContainer.needs_processing==True))
            query = query.filter(Dataset.updated_at < (datetime.datetime.now() - self.cooltime))
            data_container = query.all()
            for dc in data_container:
                if dc.needs_finding:
                    if not Job.query.filter_by(data_container=dc).filter_by(task=u'find').filter_by(status=u'new').first():
                        job = Job(data_container=dc, task=u'find')
                        dc.needs_finding = False
                        self.log.info(u'Creating %s' % job)
                if dc.needs_processing:
                    if not Job.query.filter_by(data_container=dc).filter_by(task=u'process').filter_by(status=u'new').first():
                        job = Job(data_container=dc, task=u'proc')
                        dc.needs_processing = False
                        self.log.info(u'Creating %s' % job)
            transaction.commit()
            time.sleep(self.sleeptime)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', help='database URI')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep between db queries')
        self.add_argument('-c', '--cooltime', type=int, default=60, help='time to let data cool before processing')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)

    scheduler = Scheduler(args.db_uri, log, args.sleeptime, args.cooltime)

    def term_handler(signum, stack):
        scheduler.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    scheduler.run()
    log.warning('Process halted')
