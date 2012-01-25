#!/usr/bin/env python
#
# @author: Gunnar Schaefer

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

QUANTIZATION_CORRECTION = datetime.timedelta(seconds=1)


class DataReaper(object):

    def __init__(self, datetime_file):
        super(DataReaper, self).__init__()
        self.datetime_file = datetime_file
        self.last_update = nimsutil.get_reference_datetime(self.datetime_file)
        self.monitored_files = {}
        self.alive = True

        # stage any files left behind from a previous run
        for item in os.listdir(REAP_STAGE):
            if item.startswith(REAPER_ID):
                os.rename(os.path.join(REAP_STAGE, item), os.path.join(SORT_STAGE, item))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            try:
                out = subprocess.check_output(shlex.split(DATE_FIND_CMD % (self.last_update-QUANTIZATION_CORRECTION)), stderr=subprocess.STDOUT).split()
            except subprocess.CalledProcessError:
                LOG.warning('Error while checking for new files')
            else:
                this_check = datetime.datetime.fromtimestamp(int(out[0]))
                remote_files = sorted([DataFile(*f.split(';')) for f in out[1:]], key=lambda rf: rf.mod_time)
                for rf in remote_files:
                    if rf.name in self.monitored_files:
                        mf = self.monitored_files[rf.name]
                        if rf.size == mf.size and mf.needs_reaping:
                            success = rf.reap(this_check)
                            if success:
                                nimsutil.update_reference_datetime(self.datetime_file, rf.mod_time)
                                self.last_update = rf.mod_time
                        elif mf.needs_reaping:
                            LOG.info('Monitoring %s' % rf)
                        elif rf.size == mf.size:
                            rf.needs_reaping = False
                    else:
                        LOG.info('Discovered %s' % rf)
                self.monitored_files = dict(zip([rf.name for rf in remote_files], remote_files))
            finally:
                time.sleep(SLEEP_TIME)


class DataFile(object):

    def __init__(self, name, size, mod_time, needs_reaping=True):
        self.name = name
        self.size = int(size)
        self.mod_time = datetime.datetime.fromtimestamp(int(mod_time))
        self.needs_reaping = needs_reaping

    def __repr__(self):
        return '<DataFile %s, %d, %s, %s>' % (self.name, self.size, self.mod_time, self.needs_reaping)

    def __str__(self):
        return '%s (%s bytes)' % (os.path.basename(self.name), self.size)

    def reap(self, timestamp):
        stage_dir = '%s_%s_%s' % (REAPER_ID, os.path.basename(self.name), timestamp.strftime('%s'))
        reap_path = nimsutil.make_joined_path(REAP_STAGE, stage_dir)
        try:
            LOG.info('Reaping    %s' % self)
            subprocess.check_output(shlex.split(REAP_CMD % (self.name, reap_path)), stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            shutil.rmtree(reap_path)
            success = False
            LOG.warning('Error while reaping %s' % self)
        else:
            os.rename(reap_path, os.path.join(SORT_STAGE, stage_dir))
            self.needs_reaping = False
            success = True
            LOG.info('Reaped     %s' % self)
        return success


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('stage_path', help='path to staging area')
        self.add_argument('data_host', help='username@hostname of data source')
        self.add_argument('data_path', help='path to data source')
        self.add_argument('sleep_time', help='time to sleep before checking for new data')
        self.add_argument('data_glob', nargs='?', help='glob format for files to move', default='*')
        self.add_argument('-n', '--logname', default=__file__, help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')

    def error(self, message):
        self.print_help()
        sys.exit(1)


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    REAPER_ID = os.path.basename(args.data_path.rstrip('/'))
    LOG = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    SLEEP_TIME = int(args.sleep_time)
    REAP_STAGE = nimsutil.make_joined_path(args.stage_path, 'reap')
    DATA_PATH = os.path.join(args.data_path, args.data_glob)
    SORT_STAGE = nimsutil.make_joined_path(args.stage_path, 'sort')

    DATE_CMD = 'date +%%s'
    FIND_CMD = 'find %s -maxdepth 1 -newermt "%%s" -exec stat -c "%%%%n;%%%%s;%%%%Y" {} +' % DATA_PATH
    DATE_FIND_CMD = 'ssh %s \'%s; %s\'' % (args.data_host, DATE_CMD, FIND_CMD)
    REAP_CMD = 'rsync -a %s:%%s %%s' % args.data_host

    reaper = DataReaper('.%s.datetime' % REAPER_ID)

    def term_handler(signum, stack):
        reaper.halt()
        LOG.info('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    LOG.warning('Process halted')
