#!/usr/bin/env python
#
# @author: Gunnar Schaefer

import os
import glob
import time
import shutil
import signal
import argparse
import datetime

import nimsutil


class FileReaper(object):

    def __init__(self, id_, data_glob, reap_stage, sort_stage, datetime_file, sleep_time, log):
        super(FileReaper, self).__init__()
        self.id_ = id_
        self.data_glob = data_glob
        self.reap_stage = reap_stage
        self.sort_stage = sort_stage
        self.datetime_file = datetime_file
        self.sleep_time = sleep_time
        self.log = log

        self.current_file_timestamp = nimsutil.get_reference_datetime(self.datetime_file)
        self.monitored_files = {}
        self.alive = True

        # stage any files left behind from a previous run
        for item in os.listdir(self.reap_stage):
            if item.startswith(self.id_):
                os.rename(os.path.join(self.reap_stage, item), os.path.join(self.sort_stage, item))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            reap_files = [ReapFile(f, self.id_, self.reap_stage, self.sort_stage, self.log) for f in glob.glob(data_glob)]
            reap_files = sorted(filter(lambda f: f.mod_time >= self.current_file_timestamp, reap_files), key=lambda f: f.mod_time)

            if not reap_files:
                self.log.warning('No matching files found (or error while checking for files)')
                time.sleep(self.sleep_time)
                continue

            for rf in reap_files:
                if rf.path in self.monitored_files:
                    mf = self.monitored_files[rf.path]
                    if rf.size == mf.size and mf.needs_reaping:
                        success = rf.reap()
                        if success:
                            nimsutil.update_reference_datetime(self.datetime_file, rf.mod_time)
                            self.current_file_timestamp = rf.mod_time
                    elif mf.needs_reaping:
                        self.log.info('Monitoring %s' % mf)
                    elif rf.size == mf.size:
                        rf.needs_reaping = False
                else:
                    self.log.info('Discovered %s' % rf)

            self.monitored_files = dict(zip([rf.path for rf in reap_files], reap_files))
            time.sleep(self.sleep_time)


class ReapFile(object):

    def __init__(self, path, repaer_id, reap_stage, sort_stage, log):
        self.path = path
        self.reaper_id = reaper_id
        self.reap_stage = reap_stage
        self.sort_stage = sort_stage
        self.log = log

        self.size = os.path.getsize(path)
        self.mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        self.needs_reaping = True

    def __repr__(self):
        return '<DataFile %s, %d, %s, %s>' % (os.path.basename(self.path), self.size, self.mod_time, self.needs_reaping)

    def __str__(self):
        return '%s (%s bytes)' % (os.path.basename(self.path), self.size)

    def reap(self):
        reap_path = nimsutil.make_joined_path(self.reap_stage, '%s_%s' % (self.reaper_id, datetime.datetime.now().strftime('%s.%f')))
        try:
            self.log.info('Reaping    %s' % self)
            shutil.copy2(self.path, reap_path)
        except KeyboardInterrupt:
            shutil.rmtree(reap_path)
            raise
        except (shutil.Error, IOError):
            success = False
            self.log.warning('Error while reaping %s' % self)
        else:
            shutil.move(reap_path, sort_stage)
            self.needs_reaping = False
            success = True
            self.log.info('Reaped     %s' % self)
        return success


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('stage_path', help='path to staging area')
        self.add_argument('data_path', help='path to data source')
        self.add_argument('-g', '--fileglob', default='*', help='glob for files to reap (default: "*")')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep before checking for new data')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    reaper_id = os.path.basename(args.data_path.rstrip('/'))
    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    data_glob = os.path.join(args.data_path, args.fileglob)
    reap_stage = nimsutil.make_joined_path(args.stage_path, 'reap')
    sort_stage = nimsutil.make_joined_path(args.stage_path, 'sort')
    datetime_file = os.path.join(os.path.dirname(__file__), '.%s.datetime' % reaper_id)

    reaper = FileReaper(reaper_id, data_glob, reap_stage, sort_stage, datetime_file, args.sleeptime, log)

    def term_handler(signum, stack):
        reaper.halt()
        log.info('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('Process halted')
