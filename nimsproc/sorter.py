#!/usr/bin/env python
#
# @author:  Gunnar Schaefer, Reno Bowen

import os
import time
import shutil
import logging
import datetime
import transaction

import nimsdata
import nimsgears.model

log = logging.getLogger('sorter')

import warnings
warnings.filterwarnings('error')

class Sorter(object):

    def __init__(self, stage_path, preserve_path, nims_path, sleep_time):
        super(Sorter, self).__init__()
        self.stage_path = stage_path
        self.preserve_path = preserve_path
        self.nims_path = nims_path
        self.sleep_time = sleep_time
        self.alive = True

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            stage_items = [os.path.join(self.stage_path, si) for si in os.listdir(self.stage_path) if not si.startswith('.')] # ignore dot files
            if stage_items:
                for stage_item in sorted(stage_items, key=os.path.getmtime): # oldest first
                    if os.path.islink(stage_item):
                        os.remove(stage_item)
                    elif 'gephysio' in os.path.basename(stage_item): # HACK !!!!!!!!!!!!!!!! NIMS 1.0 cannot sort gephysio
                        os.remove(stage_item)
                    elif os.path.isfile(stage_item):
                        self.sort(stage_item)
                    else:
                        for subpath in [os.path.join(dirpath, fn) for (dirpath, _, filenames) in os.walk(stage_item) for fn in filenames]:
                            if not os.path.islink(subpath) and not subpath.startswith('.'):
                                self.sort(subpath)
                        shutil.rmtree(stage_item)
            else:
                log.debug('Waiting for data...')
                time.sleep(self.sleep_time)

    def sort(self, filepath):
        filename = os.path.basename(filepath)
        try:
            log.info('Parsing     %s' % filename)
            mrfile = nimsdata.parse(filepath)
        except nimsdata.NIMSDataError:
            log.warning('Cannot sort %s' % filename)
            if self.preserve_path:
                preserve_path = os.path.join(self.preserve_path, os.path.relpath(filepath, self.stage_path).replace('/', '_'))
                log.debug('Preserving  %s' % filename)
                shutil.move(filepath, preserve_path)
        else:
            log.info('Sorting     %s' % filename)
            filename = '_'.join(filename.rsplit('_')[-4:])
            dataset = nimsgears.model.Dataset.from_mrfile(mrfile, self.nims_path)
            shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, filename))
            dataset.filenames = [filename]
            dataset.updatetime = datetime.datetime.now()
            dataset.untrash()
            transaction.commit()


if __name__ == '__main__':
    import signal
    import argparse
    import sqlalchemy

    import nimsutil

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('db_uri', help='database URI')
    arg_parser.add_argument('stage_path', help='path to staging area')
    arg_parser.add_argument('nims_path', help='data destination')
    arg_parser.add_argument('-t', '--toplevel', action='store_true', help='handle toplevel files')
    arg_parser.add_argument('-p', '--preserve_path', help='preserve unsortable files here')
    arg_parser.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep before checking for new files')
    arg_parser.add_argument('-f', '--logfile', help='path to log file')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level (default: info)')
    arg_parser.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')
    args = arg_parser.parse_args()

    nimsutil.configure_log(args.logfile, not args.quiet, args.loglevel)
    nimsgears.model.init_model(sqlalchemy.create_engine(args.db_uri))
    sorter = Sorter(args.stage_path, args.preserve_path, args.nims_path, args.sleeptime)

    def term_handler(signum, stack):
        sorter.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    sorter.run()
    log.warning('Process halted')
