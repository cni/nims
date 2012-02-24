#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

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
from nimsgears import model


class Sorter(object):

    def __init__(self, db_uri, stage_path, junk_path, data_path, sleep_time, log):
        super(Sorter, self).__init__()
        self.stage_path = stage_path
        self.junk_path = junk_path
        self.data_path = data_path
        self.sleep_time = sleep_time
        self.log = log
        self.alive = True
        model.init_model(sqlalchemy.create_engine(db_uri))
        self.mri_dataset_factory = MRIDatasetFactory()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            stage_contents = [os.path.join(self.stage_path, sc) for sc in os.listdir(self.stage_path)]
            if stage_contents:
                newest_item = max(stage_contents, key=os.path.getmtime)
                self.log.info('Sorting %s' % os.path.basename(newest_item))
                if os.path.isdir(newest_item):
                    self.sort_files(newest_item)
                else:
                    self.sort_file(newest_item)
                self.log.info('Sorted  %s' % os.path.basename(newest_item))
            else:
                self.log.debug('Waiting for work...')
                time.sleep(self.sleep_time)

    def sort_files(self, sort_dir):
        for dirpath, dirnames, filenames in os.walk(sort_dir, topdown=False):
            for filename in filenames:
                if not self.alive: return
                self.sort_file(os.path.join(dirpath, filename))
            os.rmdir(dirpath)

    def sort_file(self, filename):
        """
        Insert file, if valid, into database and associated filesystem.

        Mark dataset as needing processing.
        """
        self.log.debug('Sorting %s' % os.path.basename(filename))
        dataset = self.mri_dataset_factory.get_dataset(filename)
        if dataset:
            dest = nimsutil.make_joined_path(self.data_path, dataset.path)
            ext = dataset.filename_ext if os.path.splitext(filename)[1] != dataset.filename_ext else ''
            shutil.move(filename, os.path.join(dest, os.path.basename(filename) + ext))
            dataset.untrash()
            dataset.is_dirty = True
            dataset.updated_at = datetime.datetime.now()
            transaction.commit()
        else:
            unsort_filename = os.path.join(self.junk_path, os.path.relpath(filename, self.stage_path))
            nimsutil.make_joined_path(os.path.dirname(unsort_filename))
            os.rename(filename, unsort_filename)


class MRIDatasetFactory(object):

    def __init__(self):
        super(MRIDatasetFactory, self).__init__()
        self.dataset_classes = sorted(model.MRIDataset.__subclasses__(), key=lambda cls: cls.priority)

    def get_dataset(self, filename):
        """Return instance of appropriate MRIDataset subclass for provided file."""
        for dataset_class in self.dataset_classes:
            dataset = dataset_class.from_file(filename)
            if dataset: break
        return dataset


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('db_uri', help='database URI')
        self.add_argument('stage_path', help='path to staging area')
        self.add_argument('nims_path', help='data destination')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep before checking for new files')
        self.add_argument('-n', '--logname', default=__file__, help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')

    def error(self, message):
        self.print_help()
        sys.exit(1)


if __name__ == "__main__":
    args = ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    stage_path = nimsutil.make_joined_path(args.stage_path, 'sort')
    junk_path = nimsutil.make_joined_path(args.stage_path, 'junk')
    nims_path = nimsutil.make_joined_path(args.nims_path)

    sorter = Sorter(args.db_uri, stage_path, junk_path, nims_path, args.sleeptime, log)

    def term_handler(signum, stack):
        sorter.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    sorter.run()
    log.warning('Process halted')
