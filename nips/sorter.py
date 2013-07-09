#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import bson
import time
import shutil
import signal
import hashlib
import pymongo
import tarfile
import argparse

import nimsdata
import nimsutil


class Sorter(object):

    def __init__(self, db_uri, db_name, stage_path, sort_path, preserve_path, sleep_time, tempdir, log):
        self.db = pymongo.MongoClient(*pymongo.uri_parser.parse_host(db_uri))[db_name]
        self.stage_path = stage_path
        self.sort_path = sort_path
        self.preserve_path = preserve_path
        self.sleep_time = sleep_time
        self.tempdir = tempdir
        self.log = log
        self.alive = True

        self.db.experiments.create_index([('owner', 1), ('name', 1)])

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            stage_files = [os.path.join(self.stage_path, sf) for sf in os.listdir(self.stage_path) if not sf.startswith('.')] # ignore dot files
            if stage_files:
                stage_filepath = min(stage_files, key=os.path.getmtime)    # oldest first
                stage_filename = os.path.basename(stage_filepath)
                self.log.info('Inspecting  %s' % stage_filename)
                with nimsutil.TempDir(dir=self.tempdir) as temp_dirpath:
                    for sort_dataset, sort_filepaths in self.extract_datasets(stage_filepath, temp_dirpath):
                        self.log.info('Sorting     %s' % ', '.join([os.path.basename(sfp) for sfp in sort_filepaths]))
                        dataset_dirpath, dataset_subdoc = self.dirpath_and_subdoc_for_dataset(sort_dataset)
                        for sfp in sort_filepaths:
                            hash_ = hashlib.md5()
                            with open(sfp, 'rb') as spf_fd:
                                for chunk in iter(lambda: spf_fd.read(2**20), ''):
                                    hash_.update(chunk)
                            sfp_name, sfp_sep, sfp_ext = os.path.basename(sfp).partition('.')
                            file_subdoc = dataset_subdoc + '.files.' + sfp_ext.replace('.', '_')
                            self.db.sessions.update(sort_dataset.session_spec, {'$set': {file_subdoc: {
                                    'filename': sfp_name,
                                    'ext':      sfp_sep + sfp_ext,
                                    'size':     os.path.getsize(sfp),
                                    'md5':      hash_.hexdigest(),
                                    }}})
                            shutil.move(sfp, dataset_dirpath + '/' + os.path.basename(sfp))
                if os.path.isfile(stage_filepath):
                    os.remove(stage_filepath)
                else:
                    shutil.rmtree(stage_filepath)
                self.log.info('Done        %s' % stage_filename)
            else:
                self.log.debug('Waiting for data...')
                time.sleep(self.sleep_time)

    def extract_datasets(self, stage_filepath, temp_dirpath):
        # TODO: make this more general, nested archives, etc., probably using recursion
        if os.path.isdir(stage_filepath):
            dirpath = stage_filepath
        elif tarfile.is_tarfile(stage_filepath):
            with tarfile.open(stage_filepath, 'r:*') as archive:
                archive.extractall(temp_dirpath)
            dirpath = os.path.join(temp_dirpath, os.listdir(temp_dirpath)[0])
        else:
            return []
        datasets = []
        all_filenames = os.listdir(dirpath)
        aux_filenames = filter(lambda fn: fn.startswith('_'), all_filenames)
        sort_filenames = filter(lambda fn: not fn.startswith('_'), all_filenames)
        for sort_filename in sort_filenames:
            sort_filepath = os.path.join(dirpath, sort_filename)
            aux_filepaths = [os.path.join(dirpath, afn) for afn in aux_filenames if sort_filename.startswith(afn.lstrip('_').rpartition('_')[0])]
            dataset = nimsdata.NIMSData.parse(sort_filepath)
            if dataset:
                datasets.append((dataset, [sort_filepath] + aux_filepaths))
            elif self.preserve_path:
                stage_filename = os.path.basename(stage_filepath)
                stage_preserve_path = os.path.join(self.preserve_path, stage_filename)
                self.log.warning('Cannot sort %s of %s' % (sort_filename, stage_filename))
                if not os.path.exists(stage_preserve_path):
                    os.mkdir(stage_preserve_path)
                for sfp in [sort_filepath] + aux_filepaths:
                    shutil.move(sfp, os.path.join(stage_preserve_path, os.path.basename(sfp)))
        return datasets

    def dirpath_and_subdoc_for_dataset(self, ds):
        subj_code, lab_name, exp_name = nimsutil.parse_patient_id(ds.patient_id, [g['_id'] for g in self.db.groups.find()])
        owner = self.db.groups.find_one({'_id': lab_name})
        experiment_spec = {'owner': owner['_id'], 'name': exp_name}
        experiment = self.db.experiments.find_one(experiment_spec)
        if not experiment:
            self.db.experiments.insert(experiment_spec)
            experiment = self.db.experiments.find_one(experiment_spec)
        session = self.db.sessions.find_one(ds.session_spec)
        if not session:
            self.db.sessions.insert(ds.get_session_info(experiment=experiment['_id']))
            session = self.db.sessions.find_one(ds.session_spec)
        epoch = session['epochs'].get(ds.db_acq_key)
        subdoc = 'epochs.' + ds.db_acq_key
        if not epoch:
            updates = dict([(subdoc, ds.epoch_info)] + ([('timestamp', ds.timestamp)] if session['timestamp'] > ds.timestamp else []))
            self.db.sessions.update(ds.session_spec, {'$set': updates})
            epoch = self.db.sessions.find_one(ds.session_spec)['epochs'][ds.db_acq_key]
        dataset = epoch['datasets'].get(ds.filetype)
        subdoc += '.datasets.' + ds.filetype
        if not dataset:
            self.db.sessions.update(ds.session_spec, {'$set': {subdoc: {'_id': bson.objectid.ObjectId()}}})
            dataset = self.db.sessions.find_one(ds.session_spec)['epochs'][ds.db_acq_key]['datasets'][ds.filetype]
        path = self.sort_path + '/' + str(dataset['_id'])[-3:] + '/' + str(dataset['_id'])
        if not os.path.exists(path): os.makedirs(path)
        return path, subdoc


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('uri', help='NIMS DB URI')
        self.add_argument('db', help='NIMS DB name')
        self.add_argument('stage_path', help='path to staging area')
        self.add_argument('nims_path', help='data destination')
        self.add_argument('-p', '--preserve', help='preserve incompatible files here')
        self.add_argument('-s', '--sleeptime', type=int, default=5, help='time to sleep before checking for new files')
        self.add_argument('-t', '--tempdir', help='directory to use for temporary files')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    log = nimsutil.get_logger(args.logname, args.logfile, not args.quiet, args.loglevel)
    sorter = Sorter(args.uri, args.db, args.stage_path, args.nims_path, args.preserve, args.sleeptime, args.tempdir, log)

    def term_handler(signum, stack):
        sorter.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    sorter.run()
    log.warning('Process halted')
