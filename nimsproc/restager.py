#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import time
import shlex
import shutil
import signal
import argparse
import datetime
import subprocess

import nimsutil

class Restager(object):
    def __init__(self):
        super(Restager, self).__init__()

    def run(self):
        try:
            subprocess.check_call(shlex.split(SETUP_CMD))
        except subprocess.CalledProcessError:
            global ALIVE
            ALIVE = False
            LOG.error('Cannot set up remote staging area')

        while ALIVE:
            stage_contents = [os.path.join(LOCAL_STAGE, sc) for sc in os.listdir(LOCAL_STAGE)]
            if stage_contents:
                newest_item = max(stage_contents, key=os.path.getmtime)
                try:
                    LOG.info('Restaging %s' % os.path.basename(newest_item))
                    subprocess.check_call(shlex.split(SCP_CMD % newest_item))
                    subprocess.check_call(shlex.split(MOVE_CMD % os.path.basename(newest_item)))
                except subprocess.CalledProcessError:
                    LOG.info('Failed to restage %s' % os.path.basename(newest_item))
                else:
                    shutil.rmtree(newest_item)
                    LOG.info('Restaged  %s' % os.path.basename(newest_item))
            else:
                LOG.debug('Waiting for work...')
                time.sleep(SLEEP_TIME)

class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('data_host', help='username@hostname of data destination')
        self.add_argument('remote_stage_path', help='path to remote staging area')
        self.add_argument('local_stage_path', help='path to local staging area')
        self.add_argument('sleep_time', help='time to sleep before checking for new data')
        self.add_argument('--logport', type=int, help='port to send logging messages to')

    def error(self, message):
        self.print_help()
        sys.exit(1)

if __name__ == "__main__":
    args = ArgumentParser().parse_args()
    reap_stage = os.path.join(args.remote_stage_path, 'reap')
    sort_stage = os.path.join(args.remote_stage_path, 'sort')

    LOG = nimsutil.get_logger('restager')
    LOCAL_STAGE = nimsutil.make_joined_path(args.local_stage_path, 'sort')
    SLEEP_TIME = int(args.sleep_time)
    ALIVE = True

    SCP_CMD = 'rsync -a %%s %s:%s' % (args.data_host, reap_stage)
    MOVE_CMD = 'ssh %s \'mv %s/%%s %s\'' % (args.data_host, reap_stage, sort_stage)
    SETUP_CMD = 'ssh %s \'mkdir -p %s %s; rm -rf %s/*\'' % (args.data_host, reap_stage, sort_stage, reap_stage)

    def term_handler(signum, stack):
        global ALIVE
        ALIVE = False
        LOG.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    restager = Restager()
    restager.run()
