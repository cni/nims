#!/usr/bin/env python
#
# @author:  Gunnar Schaefer, Reno Bowen

import os
import glob
import time
import shutil
import logging
import tarfile
import datetime
import transaction

import nimsdata
import nimsgears.model
import tempdir as tempfile

log = logging.getLogger('sorter')

import warnings
warnings.filterwarnings('error')


def write_json_file(path, object_):
    with open(path, 'w') as json_file:
        json.dump(object_, json_file, default=datetime_encoder)
        json_file.write('\n')


def write_digest_file(path):
    digest_path = os.path.join(path, 'DIGEST.txt')


def create_archive(path, content, arcname, **kwargs):
    # write digest file
    digest_filepath = os.path.join(content, 'DIGEST.txt')
    open(digest_filepath, 'w').close() # touch file, so that it's included in the digest
    filenames = sorted(os.listdir(content), key=lambda fn: (fn.endswith('.json') and 1) or (fn.endswith('.txt') and 2) or fn)
    with open(digest_filepath, 'w') as digest_file:
        digest_file.write('\n'.join(filenames) + '\n')
    # create archive
    with tarfile.open(path, 'w:gz', **kwargs) as archive:
        archive.add(content, arcname, recursive=False) # add the top-level directory
        for fn in filenames:
            archive.add(os.path.join(content, fn), os.path.join(arcname, fn))


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
                        log.info('Unpacking   %s' % os.path.basename(stage_item))
                        with tempfile.TemporaryDirectory() as tempdir_path:
                            with tarfile.open(stage_item) as archive:
                                def is_within_directory(directory, target):
                                    
                                    abs_directory = os.path.abspath(directory)
                                    abs_target = os.path.abspath(target)
                                
                                    prefix = os.path.commonprefix([abs_directory, abs_target])
                                    
                                    return prefix == abs_directory
                                
                                def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                                
                                    for member in tar.getmembers():
                                        member_path = os.path.join(path, member.name)
                                        if not is_within_directory(path, member_path):
                                            raise Exception("Attempted Path Traversal in Tar File")
                                
                                    tar.extractall(path, members, numeric_owner=numeric_owner) 
                                    
                                
                                safe_extract(archive, path=tempdir_path)
                            physiodir_path = os.listdir(tempdir_path)[0]
                            for f in os.listdir(os.path.join(tempdir_path, physiodir_path)):
                                shutil.copy(os.path.join(tempdir_path, physiodir_path, f), os.path.join(self.nims_path, 'physio'))
                        log.info('Done        %s' % os.path.basename(stage_item))
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

    def preserve(self, filepath):
        if self.preserve_path:
            preserve_path = os.path.join(self.preserve_path, os.path.relpath(filepath, self.stage_path).replace('/', '_'))
            log.debug('Preserving  %s' % os.path.basename(filepath))
            shutil.move(filepath, preserve_path)


    def sort(self, filepath):
        """
        Revised sorter to handle multiple pfile acquisitions from a single series.
        Expects tgz file to contain METADATA.json and DIGEST.txt as the first files
        in the archive.
        """
        filename = os.path.basename(filepath)
        if 'pfile' in filename:
            log.info('Parsing     %s' % filename)
            with tempfile.TemporaryDirectory(dir=None) as tempdir_path:
                with tarfile.open(filepath) as archive:
                    def is_within_directory(directory, target):
                        
                        abs_directory = os.path.abspath(directory)
                        abs_target = os.path.abspath(target)
                    
                        prefix = os.path.commonprefix([abs_directory, abs_target])
                        
                        return prefix == abs_directory
                    
                    def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                    
                        for member in tar.getmembers():
                            member_path = os.path.join(path, member.name)
                            if not is_within_directory(path, member_path):
                                raise Exception("Attempted Path Traversal in Tar File")
                    
                        tar.extractall(path, members, numeric_owner=numeric_owner) 
                        
                    
                    safe_extract(archive, path=tempdir_path)
                newdata_dir = os.path.join(tempdir_path, os.listdir(tempdir_path)[0])
                try:
                    new_digest = open(os.path.join(newdata_dir, 'DIGEST.txt')).read()
                except IOError:
                    log.debug('%s has no digest' % filepath)
                    new_digest = None
                pfile = glob.glob(os.path.join(newdata_dir, 'P?????.7'))[0]
                try:
                    mrfile = nimsdata.parse(pfile, filetype='pfile', full_parse=True)
                except nimsdata.NIMSDataError:
                    self.preserve(filepath)
                else:
                    log.info('Sorting     %s' % filename)
                    filename = '_'.join(filename.rsplit('_')[-4:])
                    dataset = nimsgears.model.Dataset.from_mrfile(mrfile, self.nims_path)
                    existing_pf = glob.glob(os.path.join(self.nims_path, dataset.relpath, '*pfile.tgz'))
                    if not existing_pf:
                        shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, filename))
                    else:
                        orig_pf = existing_pf[0]
                        with tarfile.open(orig_pf) as orig_archive:
                            for ti in orig_archive:
                                if 'DIGEST.txt' in ti.name:
                                    orig_digest = orig_archive.extractfile(ti).read()
                                    break
                            else:
                                log.debug('no digest')
                                orig_digest = None
                        if (new_digest is None or orig_digest is None) or (new_digest != orig_digest):
                            log.debug('repacking')
                            with tempfile.TemporaryDirectory(dir=tempdir_path) as combined_dir:
                                with tarfile.open(orig_pf) as orig_archive:
                                    def is_within_directory(directory, target):
                                        
                                        abs_directory = os.path.abspath(directory)
                                        abs_target = os.path.abspath(target)
                                    
                                        prefix = os.path.commonprefix([abs_directory, abs_target])
                                        
                                        return prefix == abs_directory
                                    
                                    def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                                    
                                        for member in tar.getmembers():
                                            member_path = os.path.join(path, member.name)
                                            if not is_within_directory(path, member_path):
                                                raise Exception("Attempted Path Traversal in Tar File")
                                    
                                        tar.extractall(path, members, numeric_owner=numeric_owner) 
                                        
                                    
                                    safe_extract(orig_archive, path=combined_dir)
                                combineddata_dir = os.path.join(combined_dir, os.listdir(combined_dir)[0])
                                for f in glob.glob(os.path.join(newdata_dir, '*')):
                                    fn = os.path.basename(f)
                                    log.debug('MOVING %s into %s' % (f, os.path.join(combineddata_dir, fn)))
                                    shutil.move(f, os.path.join(combineddata_dir, fn))
                                log.debug(os.listdir(combineddata_dir))
                                outpath = os.path.join(tempdir_path, filename)
                                create_archive(outpath, combineddata_dir, os.path.basename(combineddata_dir), compresslevel=6)
                                shutil.move(outpath, os.path.join(self.nims_path, dataset.relpath, filename))
                            os.remove(filepath)
                        else:
                            shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, filename))

                    log.debug('file sorted into to %s' % os.path.join(self.nims_path, dataset.relpath, filename))
                    dataset.container.num_mux_cal_cycle = mrfile.num_mux_cal_cycle
                    dataset.filenames = [filename]
                    dataset.updatetime = datetime.datetime.now()
                    dataset.untrash()
                    transaction.commit()
        else:
            try:
                mrfile = nimsdata.parse(filepath)
            except nimsdata.NIMSDataError:
                self.preserve(filepath)
            else:
                mrfile.num_mux_cal_cycle = None  # dcms will never have num_mux_cal_cycles
                if mrfile.is_screenshot:
                    mrfile.acq_no = 0
                    mrfile.timestamp = datetime.datetime.strptime(datetime.datetime.strftime(mrfile.timestamp, '%Y%m%d') + '235959', '%Y%m%d%H%M%S')
                log.info('Sorting     %s' % filename)
                filename = '_'.join(filename.rsplit('_')[-4:])
                dataset = nimsgears.model.Dataset.from_mrfile(mrfile, self.nims_path)
                shutil.move(filepath, os.path.join(self.nims_path, dataset.relpath, filename))
                dataset.filenames = [filename]
                dataset.updatetime = datetime.datetime.now()
                dataset.untrash()
                transaction.commit()
        log.info('Done        %s' % filename)


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
