#!/usr/bin/env python
#
# @author: Gunnar Schaefer

import os
import time
import shlex
import signal
import logging
import argparse
import subprocess as sp

import nimsutil

log = logging.getLogger('datasyncer')


class DataSyncer(object):

    def __init__(self, data_path, sync_path, sleep_time):
        self.rsync_cmd = 'rsync -a --del %s %s' % (data_path, sync_path)
        self.sleep_time = sleep_time
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
        self.add_argument('data_path', help='path to data source')
        self.add_argument('sync_path', help='path to syncing area')
        self.add_argument('sleep_time', type=int, help='time to sleep between rsyncs')
        self.add_argument('data_glob', nargs='?', help='glob format for files to move', default='')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='log level (default: info)')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    data_path = os.path.join(args.data_path, args.data_glob) if args.data_glob else args.data_path
    nimsutil.configure_log(args.logfile, not args.quiet, args.loglevel)

    syncer = DataSyncer(data_path, args.sync_path, args.sleep_time)

    def term_handler(signum, stack):
        syncer.halt()
        log.info('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    syncer.run()
    log.warning('Process halted')
