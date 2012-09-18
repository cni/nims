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
        model.init_model(sqlalchemy.create_engine(db_uri))

    def halt(self):
        self.alive = False

    def run(self):
        """Insert files, if valid, into database and associated filesystem."""
        while self.alive:
            stage_contents = [os.path.join(self.stage_path, sc) for sc in os.listdir(self.stage_path)]
            toplevel_files = filter(lambda tlf: not os.path.isdir(tlf), stage_contents)
            if toplevel_files:
                os.mkdir(os.path.join(self.stage_path, '__toplevel__'))
                for tlf in toplevel_files:
                    shutil.move(tlf, os.path.join(self.stage_path, '__toplevel__'))
                continue
            if stage_contents:
                sort_path = min(stage_contents, key=os.path.getmtime)   # oldest first
                self.log.info('Sorting %s' % os.path.basename(sort_path))
                for dirpath, dirnames, filenames in os.walk(sort_path, topdown=False):
                    aux_paths = {}
                    for aux_file in filter(lambda fn: fn.startswith('_'), filenames):
                        main_file = aux_file.lstrip('_').rpartition('_')[0]
                        aux_paths[main_file] = aux_paths.get(main_file, []) + [os.path.join(dirpath, aux_file)]
                    filenames = filter(lambda fn: not fn.startswith('_'), filenames)
                    if self.dir_mode and filenames and not dirnames:    # at lowest sub-directory
                        self.sort_directory(dirpath, filenames, aux_paths)
                    else:
                        self.sort_files(dirpath, filenames, aux_paths)
                self.log.info('Sorted  %s' % os.path.basename(sort_path))
            else:
                self.log.debug('Waiting for work...')
                time.sleep(self.sleep_time)

    def sort_files(self, dirpath, filenames, aux_paths):
        for filepath, filename in [(os.path.join(dirpath, fn), fn) for fn in filenames]:
            if not self.alive: return
            self.log.debug('Sorting %s' % filename)
            dataset, filename_ext = self.get_dataset_and_filename_ext(filepath)
            if dataset:
                ext = filename_ext if os.path.splitext(filepath)[1] != filename_ext else ''
                shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, os.path.basename(filepath) + ext))
                for aux_path in aux_paths.get(filename, []):
                    shutil.move(aux_path, os.path.join(self.nims_path, dataset.relpath, os.path.basename(aux_path)))
                dataset.updatetime = datetime.datetime.now()
                dataset.untrash()
                transaction.commit()
            elif self.preserve_mode:
                unsort_path = nimsutil.make_joined_path(self.unsort_path, os.path.dirname(os.path.relpath(filepath, self.stage_path)))
                shutil.move(filepath, os.path.join(unsort_path, filename))
        shutil.rmtree(dirpath)

    def sort_directory(self, dirpath, filenames, aux_paths):
        self.log.debug('Sorting %s in directory mode' % os.path.basename(dirpath))
        dataset, filename_ext = self.get_dataset_and_filename_ext(os.path.join(dirpath, filenames[0]))
        if dataset:
            for filepath, aux_paths in [(os.path.join(dirpath, filename), aux_paths.get(filename, [])) for filename in filenames]:
                ext = filename_ext if os.path.splitext(filepath)[1] != filename_ext else ''
                shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, os.path.basename(filepath) + ext))
                for aux_path in aux_paths:
                    shutil.move(aux_path, os.path.join(self.nims_path, dataset.relpath, os.path.basename(aux_path)))
            dataset.updatetime = datetime.datetime.now()
            dataset.untrash()
            transaction.commit()
        elif self.preserve_mode:
            unsort_path = nimsutil.make_joined_path(self.unsort_path, os.path.relpath(dirpath, self.stage_path))
            for filename in os.listdir(dirpath):
                shutil.move(os.path.join(dirpath, filename), os.path.join(unsort_path, filename))
        shutil.rmtree(dirpath)

    def get_dataset_and_filename_ext(self, filename):
        for datatype in (nimsutil.dicomutil.DicomFile, nimsutil.pfile.PFile):
            try:
                mrfile = datatype(filename)
            except:
                mrfile = None
            else:
                break
        if mrfile:
            dataset = model.PrimaryMRData.from_mrfile(mrfile, self.nims_path)
            filename_ext = mrfile.filename_ext
        else:
            dataset, filename_ext = (None, None)
        return dataset, filename_ext


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
