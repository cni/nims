#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import re
import sys
import glob
import gzip
import json
import time
import shutil
import signal
import hashlib
import httplib
import tarfile
import argparse
import datetime
import urlparse
import bson.json_util

import scu
import nimsdata
import nimsutil

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class Reaper(object):

    def __init__(self, id_, url, pat_id, discard_ids, peripheral_data, sleep_time, tempdir, log):
        self.id_ = id_
        self.api_url = urlparse.urlparse(url)
        self.pat_id = pat_id
        self.discard_ids = discard_ids
        self.peripheral_data = peripheral_data
        self.sleep_time = sleep_time
        self.tempdir = tempdir
        self.log = log
        self.datetime_file = os.path.join(os.path.dirname(__file__), '.%s.datetime' % self.id_)
        self.alive = True

    def halt(self):
        self.alive = False

    def get_reference_datetime(self):
        if os.access(self.datetime_file, os.R_OK):
            with open(self.datetime_file, 'r') as f:
                ref_datetime = datetime.datetime.strptime(f.readline(), DATE_FORMAT + '\n')
        else:
            ref_datetime = datetime.datetime.now()
            self.set_reference_datetime(ref_datetime)
        return ref_datetime
    def set_reference_datetime(self, new_datetime):
        with open(self.datetime_file, 'w') as f:
            f.write(new_datetime.strftime(DATE_FORMAT + '\n'))
    reference_datetime = property(get_reference_datetime, set_reference_datetime)

    def retrieve_peripheral_data(self, tempdir_path, reap_path, reap_data, reap_name, log_info):
        for pdn, pdp in self.peripheral_data.iteritems():
            if pdn in self.peripheral_data_fn_map:
                self.peripheral_data_fn_map[pdn](self, pdn, pdp, tempdir_path, reap_path, reap_data, reap_name, log_info)
            else:
                self.log.warning('Periph data %s %s does not exist' % (log_info, pdn))

    def retrieve_peripheral_physio(self, name, data_path, tempdir_path, reap_path, reap_data, reap_name, log_info):
        lower_time_bound = reap_data.timestamp + reap_data.prescribed_duration - datetime.timedelta(seconds=15)
        upper_time_bound = reap_data.timestamp + reap_data.prescribed_duration + datetime.timedelta(seconds=75)
        sleep_time = (upper_time_bound - datetime.datetime.now()).total_seconds()
        if sleep_time > 0:
            self.log.info('Periph data %s waiting for %s for %d seconds' % (log_info, name, sleep_time))
            time.sleep(sleep_time)

        while True:
            try:
                physio_files = os.listdir(self.peripheral_data[name])
            except OSError:
                physio_files = []
            if physio_files:
                break
            else:
                self.log.warning('Periph data %s %s temporarily unavailable' % (log_info, name))
                time.sleep(5)

        physio_tuples = filter(lambda pt: pt[0], [(re.match('.+_%s_([0-9_]+)' % reap_data.psd_name, pfn), pfn) for pfn in physio_files])
        physio_tuples = [(datetime.datetime.strptime(pts.group(1), '%m%d%Y%H_%M_%S_%f'), pfn) for pts, pfn in physio_tuples]
        physio_tuples = filter(lambda pt: lower_time_bound <= pt[0] <= upper_time_bound, physio_tuples)
        if physio_tuples:
            self.log.info('Periph data %s %s found' % (log_info, name))
            physio_reap_path = os.path.join(tempdir_path, name)
            os.mkdir(physio_reap_path)
            with open(os.path.join(physio_reap_path, '%s_%s.json' % (reap_name, name)), 'w') as metadata:
                json.dump(reap_data.db_info, metadata, default=bson.json_util.default)
            for pts, pfn in physio_tuples:
                shutil.copy2(os.path.join(self.peripheral_data[name], pfn), physio_reap_path)
            with tarfile.open(os.path.join(reap_path, '%s_%s.tgz' % (reap_name, name)), 'w:gz', compresslevel=6) as archive:
                archive.add(physio_reap_path, arcname=name)
        else:
            self.log.info('Periph data %s %s not found' % (log_info, name))

    peripheral_data_fn_map = {
            'physio':   retrieve_peripheral_physio
            }

    def upload(self, path, log_info):
        filepath = '%s.tar' % path
        filename = os.path.basename(filepath)
        with tarfile.open(filepath, 'w') as archive:
            archive.add(path, arcname=os.path.basename(path))
        self.log.info('Hashing     %s %s' % (log_info, filename))
        hash_ = hashlib.md5()
        with open(filepath, 'rb') as fd:
            for chunk in iter(lambda: fd.read(1048577 * hash_.block_size), ''):
                hash_.update(chunk)
        self.log.info('Uploading   %s %s' % (log_info, filename))
        with open(filepath, 'rb') as upload_file:
            success = False
            http_conn = httplib.HTTPConnection(self.api_url.netloc)
            try:
                http_conn.request('PUT', '%s?md5=%s' % (os.path.join(self.api_url.path, filename), hash_.hexdigest()), upload_file)
                response = http_conn.getresponse()
            except httplib.socket.error:
                self.log.warning('Error       %s %s' % (log_info, filename))
            else:
                if response.status == 200:
                    success = True
                    self.log.debug('Success     %s %s' % (log_info, filename))
                else:
                    self.log.warning('Failure     %s %s: %s %s' % (log_info, filename, response.status, response.reason))
        return success


class DicomReaper(Reaper):

    def __init__(self, url, arg_str, pat_id, discard_ids, peripheral_data, sleep_time, tempdir, log):
        self.scu = scu.SCU(*arg_str.split(':'), log=log)
        super(DicomReaper, self).__init__(self.scu.aec, url, pat_id, discard_ids, peripheral_data, sleep_time, tempdir, log)

    def run(self):
        monitored_exam = None
        current_exam_datetime = self.reference_datetime
        while self.alive:
            query_params = {'StudyDate': current_exam_datetime.strftime('%Y%m%d-')}
            if self.pat_id:
                query_params['PatientID'] = self.pat_id
            outstanding_exams = []
            for resp in self.scu.find(scu.StudyQuery(**query_params)):
                exam_datetime = datetime.datetime.strptime(resp.StudyDate + resp.StudyTime, '%Y%m%d%H%M%S')
                if exam_datetime >= current_exam_datetime:
                    outstanding_exams.append(self.Exam(self, resp.StudyID, resp.PatientID, exam_datetime))
            outstanding_exams = sorted(outstanding_exams, key=lambda exam: exam.timestamp)

            if monitored_exam and outstanding_exams and monitored_exam.id_ != outstanding_exams[0].id_:
                self.log.warning('Dropping    %s (assumed deleted from scanner)' % monitored_exam)
                monitored_exam = None
                continue

            next_exam = None
            out_ex_cnt = len(outstanding_exams)
            if not monitored_exam and out_ex_cnt > 0:
                next_exam = outstanding_exams[0]
            elif monitored_exam and out_ex_cnt > 1:
                if not any([series.needs_reaping for series in monitored_exam.series_dict.itervalues()]):
                    next_exam = outstanding_exams[1]

            if next_exam:
                self.reference_datetime = current_exam_datetime = next_exam.timestamp
                if next_exam.pat_id in self.discard_ids:
                    self.log.info('Discarding  %s' % next_exam)
                    current_exam_datetime += datetime.timedelta(seconds=1)
                    monitored_exam = None
                else:
                    self.log.info('New         %s' % next_exam)
                    monitored_exam = next_exam
            if monitored_exam and self.alive:
                monitored_exam.reap()
            if int(bool(monitored_exam)) + 1 > out_ex_cnt:  # sleep, if there is no queue
                time.sleep(self.sleep_time)


    class Exam(object):

        def __init__(self, reaper, id_, pat_id, timestamp):
            self.reaper = reaper
            self.id_ = id_
            self.pat_id = pat_id
            self.timestamp = timestamp
            self.series_dict = {}

        def __str__(self):
            return 'e%s %s (%s)' % (self.id_, self.timestamp, self.pat_id)

        def reap(self):
            """An exam must be reaped at least twice, since newly encountered series are not immediately reaped."""
            series_list = []
            for resp in self.reaper.scu.find(scu.SeriesQuery(StudyID=self.id_)):
                series_list.append(self.Series(self.reaper, self, resp.SeriesNumber, resp.SeriesInstanceUID, int(resp.ImagesInAcquisition)))
            for series in series_list:
                if not self.reaper.alive: break
                if series.id_ in self.series_dict:
                    self.series_dict[series.id_].reap(series.image_count)
                else:
                    self.reaper.log.info('New         %s' % series)
                    self.series_dict[series.id_] = series


        class Series(object):

            def __init__(self, reaper, exam, id_, uid, image_count):
                self.reaper = reaper
                self.exam = exam
                self.id_ = id_
                self.uid = uid
                self.image_count = image_count
                self.needs_reaping = True
                self.name_prefix = '%s_%s' % (self.exam.id_, self.id_)
                self.log_info = 'e%s, s%s' % (self.exam.id_, self.id_)

            def __str__(self):
                return '%s, %di' % (self.log_info, self.image_count)

            def reap(self, new_image_count):
                if new_image_count > self.image_count:
                    self.image_count = new_image_count
                    self.needs_reaping = True
                    self.reaper.log.debug('Monitoring  %s' % self)
                elif self.needs_reaping: # image count has stopped increasing
                    self.reaper.log.info('Reaping     %s' % self)
                    with nimsutil.TempDir(dir=reaper.tempdir) as tempdir_path:
                        reap_path = '%s/%s_%s_%s' % (tempdir_path, self.reaper.id_, self.name_prefix, datetime.datetime.now().strftime('%s'))
                        os.mkdir(reap_path)
                        reap_count = self.reaper.scu.move(scu.SeriesQuery(SeriesInstanceUID=self.uid), reap_path)
                        if reap_count == self.image_count:
                            acq_info_dict = self.split_into_acquisitions(reap_path)
                            for acq_no, acq_info in acq_info_dict.iteritems():
                                acq_tempdir_path = os.path.join(tempdir_path, str(acq_no))
                                os.mkdir(acq_tempdir_path)
                                reaper.retrieve_peripheral_data(acq_tempdir_path, reap_path, *acq_info)
                            if reaper.upload(reap_path, self.log_info):
                                self.needs_reaping = False
                                self.reaper.log.info('Done        %s' % self)
                        else:
                            self.reaper.log.warning('Incomplete  %s, %d reaped' % (self, reap_count))

            def split_into_acquisitions(self, series_path):
                self.reaper.log.info('Compressing %s' % self)
                dcm_dict = {}
                acq_info_dict = {}
                for filepath in [os.path.join(series_path, filename) for filename in os.listdir(series_path)]:
                    dcm = nimsdata.nimsdicom.NIMSDicom(filepath)
                    os.utime(filepath, (int(dcm.timestamp.strftime('%s')), int(dcm.timestamp.strftime('%s'))))  # correct timestamps
                    dcm_dict.setdefault(dcm.acq_no, []).append(filepath)
                for acq_no, acq_paths in dcm_dict.iteritems():
                    arcdir_path = os.path.join(series_path, '%s_%s_dicoms' % (self.name_prefix, acq_no))
                    arc_path = '%s.tgz' % arcdir_path
                    dcm = nimsdata.nimsdicom.NIMSDicom(acq_paths[0])
                    acq_info_dict[acq_no] = (dcm, '%s_%s' % (self.name_prefix, acq_no), '%s, a%s' % (self.log_info, acq_no))
                    os.mkdir(arcdir_path)
                    for filepath in acq_paths:
                        os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, os.path.basename(filepath)))
                    with tarfile.open('%s.tgz' % arcdir_path, 'w:gz', compresslevel=6) as archive:
                        archive.add(arcdir_path, arcname='dicoms')
                    shutil.rmtree(arcdir_path)
                return acq_info_dict


class PFileReaper(Reaper):

    def __init__(self, url, data_path, pat_id, discard_ids, peripheral_data, sleep_time, tempdir, log):
        self.data_glob = os.path.join(data_path, 'P*.7')
        id_ = data_path.strip('/').replace('/', '_')
        super(PFileReaper, self).__init__(id_, url, pat_id, discard_ids, peripheral_data, sleep_time, tempdir, log)

    def run(self):
        current_file_datetime = self.reference_datetime
        monitored_files = {}
        while self.alive:
            try:
                reap_files = [self.ReapPFile(self, p) for p in glob.glob(self.data_glob)]
                if not reap_files:
                    raise Warning('No matching files found (or error while checking for files)')
            except (OSError, Warning) as e:
                self.log.warning(e)
            else:
                reap_files = sorted(filter(lambda f: f.mod_time >= current_file_datetime, reap_files), key=lambda f: f.mod_time)
                for rf in reap_files:
                    rf.parse_pfile()
                    if rf.path in monitored_files:
                        mf = monitored_files[rf.path]
                        if mf.needs_reaping and rf.size == mf.size:
                            rf.reap()
                            if not rf.needs_reaping:
                                self.reference_datetime = current_file_datetime = rf.mod_time
                        elif mf.needs_reaping:
                            self.log.debug('Monitoring  %s' % rf)
                        elif rf.size == mf.size:
                            rf.needs_reaping = False
                    elif rf.pfile is None:
                        rf.needs_reaping = False
                        self.log.warning('Skipping    %s' (unparsable) % self.basename)
                    elif rf.pfile.patient_id.strip('/') in self.discard_ids:
                        rf.needs_reaping = False
                        self.log.info('Discarding  %s' % rf)
                    elif self.pat_id and not re.match(self.pat_id.replace('*','.*'), rf.pfile.patient_id) or rf.size > 1*2**30: # FIXME  remove !!!!!!!!!!!!!!!!!!
                        rf.needs_reaping = False
                        self.log.info('Ignoring    %s' % rf)
                    else:
                        self.log.info('Discovered  %s' % rf)
                monitored_files = dict(zip([rf.path for rf in reap_files], reap_files))
            finally:
                if len(monitored_files) < 2:
                    time.sleep(self.sleep_time)


    class ReapPFile(object):

        def __init__(self, reaper, path):
            self.reaper = reaper
            self.path = path
            self.basename = os.path.basename(path)
            self.mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            self.size = os.path.getsize(path)
            self.needs_reaping = True

        def __str__(self):
            return '%s (%s) e%s s%s a%s' % (self.log_info, self.pfile.patient_id, self.pfile.exam_no, self.pfile.series_no, self.pfile.acq_no)

        def parse_pfile(self):
            try:
                self.pfile = nimsdata.nimsraw.NIMSPFile(self.path)
            except nimsdata.nimsraw.NIMSPFileError:
                self.pfile = None
            else:
                self.name_prefix = '%s_%s_%s' % (self.pfile.exam_no, self.pfile.series_no, self.pfile.acq_no)
                self.log_info = '%s [%s] %s' % (self.basename, nimsutil.hrsize(self.size), self.mod_time.strftime(DATE_FORMAT))

        def reap(self):
            with nimsutil.TempDir(dir=reaper.tempdir) as tempdir_path:
                reap_path = '%s/%s_%s_%s' % (tempdir_path, self.reaper.id_, self.name_prefix, datetime.datetime.now().strftime('%s'))
                os.mkdir(reap_path)
                aux_reap_files = [arf for arf in glob.glob(self.path + '_*') if open(arf).read(32) == self.pfile.header.series.series_uid]
                try:
                    self.reaper.log.info('Reaping.gz  %s' % self)
                    reap_filepath = os.path.join(reap_path, self.basename + '.gz')
                    with gzip.open(reap_filepath, 'wb', compresslevel=6) as gzfile:
                        with open(self.path) as reapfile:
                            gzfile.writelines(reapfile)
                    shutil.copystat(self.path, reap_filepath)
                    os.chmod(reap_filepath, 0o644)
                    for arf in aux_reap_files:
                        arf_basename = os.path.basename(arf)
                        self.reaper.log.info('Reaping     %s' % '_' + arf_basename)
                        shutil.copy2(arf, os.path.join(reap_path, '_' + arf_basename))
                except (shutil.Error, IOError):
                    self.reaper.log.warning('Error while reaping %s' % self)
                else:
                    reaper.retrieve_peripheral_data(tempdir_path, reap_path, self.pfile, self.name_prefix, self.log_info)
                    if reaper.upload(reap_path, str(self)):
                        self.needs_reaping = False
                        self.reaper.log.info('Done        %s' % self)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('cls', metavar='class', help='Reaper subclass to use')
        self.add_argument('class_args', help='subclass arguments')
        self.add_argument('url', help='upload URL')
        self.add_argument('-d', '--discard', default='discard', help='space-separated list of Patient IDs to discard')
        self.add_argument('-i', '--patid', help='glob for Patient IDs to reap (default: "*")')
        self.add_argument('-p', '--peripheral', nargs=2, action='append', help='path to peripheral data')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep before checking for new data')
        self.add_argument('-t', '--tempdir', help='directory to use for temporary files')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()

    try:
        reaper_cls = getattr(sys.modules[__name__], args.cls)
    except AttributeError:
        print 'ERROR: %s is not a valid Reaper class' % args.cls
        sys.exit(1)

    log = nimsutil.get_logger(args.logname, args.logfile, not args.quiet, args.loglevel)
    reaper = reaper_cls(args.url, args.class_args, args.patid, args.discard.split(), dict(args.peripheral), args.sleeptime, args.tempdir, log)

    def term_handler(signum, stack):
        reaper.halt()
        log.warning('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('Process halted')
