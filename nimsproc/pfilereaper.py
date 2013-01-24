#!/usr/bin/env python
#
# @author: Gunnar Schaefer

import re
import os
import glob
import time
import shutil
import signal
import argparse
import datetime

import nimsutil


class PFileReaper(object):

    def __init__(self, id_, pat_id, discard_ids, data_path, reap_path, sort_path, datetime_file, sleep_time, log):
        super(PFileReaper, self).__init__()
        self.id_ = id_
        self.pat_id = pat_id
        self.discard_ids = discard_ids
        self.data_glob = os.path.join(data_path, 'P?????.7')
        self.reap_stage = nimsutil.make_joined_path(reap_path)
        self.sort_stage = nimsutil.make_joined_path(sort_path)
        self.datetime_file = datetime_file
        self.sleep_time = sleep_time
        self.log = log

        self.current_file_timestamp = nimsutil.get_reference_datetime(self.datetime_file)
        self.monitored_files = {}
        self.alive = True

        # delete any files left behind from a previous run
        for item in os.listdir(self.reap_stage):
            if item.startswith(self.id_):
                shutil.rmtree(os.path.join(self.reap_stage, item))
        for item in os.listdir(self.sort_stage):
            if item.startswith('.' + self.id_):
                shutil.rmtree(os.path.join(self.sort_stage, item))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            try:
                reap_files = [ReapPFile(p, self) for p in glob.glob(self.data_glob)]
                if not reap_files:
                    raise Warning('No matching files found (or error while checking for files)')
            except (OSError, Warning) as e:
                self.log.warning(e)
            else:
                reap_files = sorted(filter(lambda f: f.mod_time >= self.current_file_timestamp, reap_files), key=lambda f: f.mod_time)
                for rf in reap_files:
                    if rf.path in self.monitored_files:
                        mf = self.monitored_files[rf.path]
                        if rf.size == mf.size and mf.needs_reaping:
                            success = rf.reap()
                            if success:
                                nimsutil.update_reference_datetime(self.datetime_file, rf.mod_time)
                                self.current_file_timestamp = rf.mod_time
                        elif mf.needs_reaping:
                            self.log.info('Monitoring  %s' % rf)
                        elif rf.size == mf.size:
                            rf.needs_reaping = False
                    else:
                        self.log.info('Discovered  %s' % rf)
                self.monitored_files = dict(zip([rf.path for rf in reap_files], reap_files))
            finally:
                time.sleep(self.sleep_time)


class ReapPFile(object):

    def __init__(self, path, reaper):
        self.path = path
        self.basename = os.path.basename(path)
        self.reaper = reaper
        self.pat_id = None
        self.size = os.path.getsize(path)
        self.mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        self.needs_reaping = True

    def __repr__(self):
        return '<ReapPFile %s, %d, %s, %s>' % (self.basename, self.size, self.mod_time, self.needs_reaping)

    def __str__(self):
        info = ' (%s) %s_%s_%s' % (self.pat_id, self.exam, self.series, self.acq) if self.pat_id else ''
        return '%s [%s]%s' % (self.basename, nimsutil.hrsize(self.size), info)

    def reap(self):
        pfile = nimsutil.pfile.PFile(self.path)
        self.pat_id = pfile.patient_id
        self.exam = pfile.exam_no
        self.series = pfile.series_no
        self.acq = pfile.acq_no
        stage_dir = '%s_%s' % (self.reaper.id_, datetime.datetime.now().strftime('%s.%f'))
        reap_path = nimsutil.make_joined_path(self.reaper.reap_stage, stage_dir)
        aux_reap_files = [arf for arf in glob.glob(self.path + '_*') if open(arf).read(32) == pfile.header.series.series_uid]
        if self.pat_id.strip('/') in reaper.discard_ids:
            self.needs_reaping = False
            self.reaper.log.info('Discarding  %s' % self)
            return True
        if self.reaper.pat_id and not re.match(self.reaper.pat_id.replace('*','.*'), self.pat_id):
            self.needs_reaping = False
            self.reaper.log.info('Ignoring    %s' % self)
            return True
        try:
            self.reaper.log.info('Reaping     %s' % self)
            shutil.copy2(self.path, reap_path)
            for arf in aux_reap_files:
                shutil.copy2(arf, os.path.join(reap_path, '_' + os.path.basename(arf)))
                self.reaper.log.info('Reaping     %s' % '_' + os.path.basename(arf))
        except KeyboardInterrupt:
            shutil.rmtree(reap_path)
            raise
        except (shutil.Error, IOError):
            success = False
            self.reaper.log.warning('Error while reaping %s' % self)
        else:
            self.reaper.log.info('Compressing %s' % self)
            nimsutil.gzip_inplace(os.path.join(reap_path, self.basename), 0o644)
            shutil.move(reap_path, os.path.join(self.reaper.sort_stage, '.' + stage_dir))
            os.rename(os.path.join(self.reaper.sort_stage, '.' + stage_dir), os.path.join(self.reaper.sort_stage, stage_dir))
            self.needs_reaping = False
            success = True
            self.reaper.log.info('Reaped      %s' % self)
        return success


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('reap_path', help='path to reaping stage')
        self.add_argument('sort_path', help='path to sorting stage')
        self.add_argument('data_path', help='path to data source')
        self.add_argument('-p', '--patid', help='glob for patient IDs to reap (default: "*")')
        self.add_argument('-d', '--discard', default='discard', help='space-separated list of Patient IDs to discard')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep before checking for new data')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    reaper_id = args.data_path.strip('/').replace('/', '_')
    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    datetime_file = os.path.join(os.path.dirname(__file__), '.%s.datetime' % reaper_id)

    reaper = PFileReaper(reaper_id, args.patid, args.discard.split(), args.data_path, args.reap_path, args.sort_path, datetime_file, args.sleeptime, log)

    def term_handler(signum, stack):
        reaper.halt()
        log.info('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('Process halted')
