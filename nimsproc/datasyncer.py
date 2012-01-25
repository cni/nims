#!/usr/bin/env python
#
# @author: Gunnar Schaefer

import os
import sys
import time
import shlex
import signal
import argparse
import subprocess as sp

import nimsutil

RSYNC_CMD = 'rsync -a --del %s:%s %s'


class DataSyncer(object):

    def __init__(self, data_host, data_path, sync_path, sleep_time, log):
        self.rsync_cmd = RSYNC_CMD % (data_host, data_path, sync_path)
        self.sleep_time = sleep_time
        self.log = log
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            try:
                sp.check_call(shlex.split(self.rsync_cmd), stdout=open('/dev/null', 'w'), stderr=sp.STDOUT)
            except sp.CalledProcessError:
                log.warning('Error while syncing remote files')
            else:
                log.debug('Remote files synced successfully')
            finally:
                time.sleep(self.sleep_time)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('sync_path', help='path to syncing area')
        self.add_argument('data_host', help='username@hostname of data source')
        self.add_argument('data_path', help='path to data source')
        self.add_argument('sleep_time', type=int, help='time to sleep between rsyncs')
        self.add_argument('data_glob', nargs='?', help='glob format for files to move', default='')
        self.add_argument('-n', '--logname', default=__file__, help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')

    def error(self, message):
        self.print_help()
        sys.exit(1)


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    data_path = os.path.join(args.data_path, args.data_glob) if args.data_glob else args.data_path
    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)

    syncer = DataSyncer(args.data_host, data_path, args.sync_path, args.sleep_time, log)

    def term_handler(signum, stack):
        syncer.halt()
        log.info('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    syncer.run()
    log.warning('Process halted')
