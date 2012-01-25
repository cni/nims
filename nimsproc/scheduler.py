#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import sys
import time
import signal
import argparse
import datetime

import sqlalchemy
import transaction

import nimsutil
from nimsgears import model


class Scheduler(object):

    def __init__(self, db_uri, log, sleeptime, cooltime):
        super(Scheduler, self).__init__()
        self.log = log
        self.sleeptime = sleeptime
        self.cooltime = cooltime
        self.alive = True
        model.init_model(sqlalchemy.create_engine(db_uri))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            query = model.Dataset.query.with_lockmode('update') # update necessary???
            query = query.filter_by(is_dirty=True)
            query = query.filter(model.Dataset.updated_at < (datetime.datetime.now() - self.cooltime))
            datasets = query.all()

            for ds in datasets:
                for task in ds.tasks:
                    if not model.Job.query.filter_by(dataset=ds).filter_by(task=task).filter_by(status=u'new').first():
                        job = model.Job(dataset=ds, task=task, max_workers=2)
                        self.log.info(u'Adding %s' % job)
                ds.is_dirty = False
            transaction.commit()
            time.sleep(self.sleeptime)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('db_uri', help='database URI')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep between db queries')
        self.add_argument('-c', '--cooltime', type=int, default=60, help='time to let data cool before processing')
        self.add_argument('-n', '--logname', default=__file__, help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')

    def error(self, message):
        self.print_help()
        sys.exit(1)


if __name__ == "__main__":
    args = ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    cooltime = datetime.timedelta(seconds=args.cooltime)

    scheduler = Scheduler(args.db_uri, log, args.sleeptime, cooltime)

    def term_handler(signum, stack):
        scheduler.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    scheduler.run()
    log.warning('Process halted')
