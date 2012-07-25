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

    def __init__(self, db_uri, stage_path, unsort_path, nims_path, dir_mode, preserve_mode, sleep_time, log):
        super(Sorter, self).__init__()
        self.stage_path = stage_path
        self.unsort_path = unsort_path
        self.nims_path = nims_path
        self.dir_mode = dir_mode
        self.preserve_mode = preserve_mode
        self.sleep_time = sleep_time
        self.log = log
        self.alive = True
        self.dataset_classes = sorted(model.PrimaryMRData.__subclasses__(), key=lambda cls: cls.priority)
        model.init_model(sqlalchemy.create_engine(db_uri))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            stage_contents = [os.path.join(self.stage_path, sc) for sc in os.listdir(self.stage_path)]
            if stage_contents:
                sort_path = min(stage_contents, key=os.path.getmtime)   # oldest first
                self.log.info('Sorting %s' % os.path.basename(sort_path))
                if os.path.isdir(sort_path):
                    self.sort_files(sort_path)
                else:
                    self.sort_file(sort_path)
                self.log.info('Sorted  %s' % os.path.basename(sort_path))
            else:
                self.log.debug('Waiting for work...')
                time.sleep(self.sleep_time)

    def sort_files(self, sort_path):
        """Insert files, if valid, into database and associated filesystem."""
        for dirpath, dirnames, filenames in os.walk(sort_path, topdown=False):
            if self.dir_mode and filenames and not dirnames:    # at lowest sub-directory
                self.sort_directory(dirpath, filenames)
            else:
                for filename in filenames:
                    if not self.alive: return
                    self.sort_file(os.path.join(dirpath, filename))
        shutil.rmtree(sort_path)

    def sort_file(self, filepath):
        self.log.debug('Sorting %s' % os.path.basename(filepath))
        dataset = self.dataset_at_path(self.nims_path, filepath)
        if dataset:
            ext = dataset.filename_ext if os.path.splitext(filepath)[1] != dataset.filename_ext else ''
            shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, os.path.basename(filepath) + ext))
            dataset.updatetime = datetime.datetime.now()
            dataset.untrash()
            transaction.commit()
        elif self.preserve_mode:
            unsort_path = nimsutil.make_joined_path(self.unsort_path, os.path.dirname(os.path.relpath(filepath, self.stage_path)))
            shutil.move(filepath, unsort_path)
        else:
            os.remove(filepath)

    def sort_directory(self, dirpath, filenames):
        self.log.debug('Sorting %s in directory mode' % os.path.basename(dirpath))
        dataset = self.dataset_at_path(self.nims_path, os.path.join(dirpath, filenames[0]))
        if dataset:
            for filepath in [os.path.join(dirpath, filename) for filename in filenames]:
                ext = dataset.filename_ext if os.path.splitext(filepath)[1] != dataset.filename_ext else ''
                shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, os.path.basename(filepath) + ext))
            dataset.updatetime = datetime.datetime.now()
            dataset.untrash()
            transaction.commit()
        elif self.preserve_mode:
            unsort_path = nimsutil.make_joined_path(self.unsort_path, os.path.dirname(os.path.relpath(dirpath, self.stage_path)))
            shutil.move(dirpath, unsort_path)

    def dataset_at_path(self, nims_path, filepath):
        """Return instance of appropriate MRIDataset subclass for provided file."""
        for dataset_class in self.dataset_classes:
            dataset = dataset_class.at_path(nims_path, filepath)
            if dataset: break
        return dataset


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', help='database URI')
        self.add_argument('stage_path', help='path to staging area')
        self.add_argument('nims_path', help='data destination')
        self.add_argument('-d', '--dirmode', action='store_true', help='assume files are pre-sorted by directory')
        self.add_argument('-p', '--preserve', action='store_true', help='preserve unsortable files')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep before checking for new files')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    stage_path = nimsutil.make_joined_path(args.stage_path, 'sort')
    unsort_path = nimsutil.make_joined_path(args.stage_path, 'unsortable')
    nims_path = nimsutil.make_joined_path(args.nims_path)

    sorter = Sorter(args.db_uri, stage_path, unsort_path, nims_path, args.dirmode, args.preserve, args.sleeptime, log)

    def term_handler(signum, stack):
        sorter.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    sorter.run()
    log.warning('Process halted')
