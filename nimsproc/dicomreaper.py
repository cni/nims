#!/usr/bin/env python
#
# @author:  Gunnar Schaefer
#           Reno Bowen

import os
import sys
import time
import shutil
import signal
import tarfile
import argparse
import datetime
import collections

import dicom

import scu
import nimsutil


class DicomReaper(object):

    def __init__(self, id_, scu, pat_id, discard_ids, reap_path, sort_path, datetime_file, sleep_time, log):
        self.id_ = id_
        self.scu = scu
        self.pat_id = pat_id
        self.discard_ids = discard_ids
        self.reap_stage = nimsutil.make_joined_path(reap_path)
        self.sort_stage = nimsutil.make_joined_path(sort_path)
        self.datetime_file = datetime_file
        self.sleep_time = sleep_time
        self.log = log

        self.current_exam_datetime = nimsutil.get_reference_datetime(self.datetime_file)
        self.monitored_exams = collections.deque()
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
            outstanding_exams = self.get_outstanding_exams()
            n_monitored_exams = len(self.monitored_exams)
            n_outstanding_exams = len(outstanding_exams)

            if n_monitored_exams > 0 and n_outstanding_exams > 0 and self.monitored_exams[0].id_ != outstanding_exams[0].id_:
                vanished_exam = self.monitored_exams.popleft()
                self.log.warning('Dropping    %s (assumed deleted from scanner)' % vanished_exam)
                continue

            if n_monitored_exams > 1 and n_outstanding_exams > 1 and self.monitored_exams[1].id_ != outstanding_exams[1].id_:
                vanished_exam = self.monitored_exams.pop()
                self.log.warning('Dropping    %s (assumed deleted from scanner)' % vanished_exam)
                continue

            next_exam = None
            if n_monitored_exams < 2 and n_monitored_exams < n_outstanding_exams:
                next_exam = outstanding_exams[n_monitored_exams]
                self.monitored_exams.append(next_exam)
            elif n_monitored_exams == 2 and n_monitored_exams < n_outstanding_exams:
                if not any([series.needs_reaping for series in self.monitored_exams[0].series_dict.itervalues()]):
                    self.monitored_exams.popleft()
                    next_exam = outstanding_exams[n_monitored_exams]
                    self.monitored_exams.append(next_exam)
                    self.current_exam_datetime = self.monitored_exams[0].datetime
                    nimsutil.update_reference_datetime(self.datetime_file, self.current_exam_datetime)

            if next_exam:
                self.log.info('New         %s' % self.monitored_exams[-1])

            for exam in self.monitored_exams:
                if not self.alive: return
                exam.reap()

            time.sleep(self.sleep_time)

    def get_outstanding_exams(self):
        query_params = {'StudyDate': self.current_exam_datetime.strftime('%Y%m%d-')}    # this should really be 'datetime - 1 day'
        if self.pat_id:
            query_params['PatientID'] = self.pat_id
        response_list = self.scu.find(scu.StudyQuery(**query_params))
        exam_list = []
        for resp in response_list:
            datetime_obj = datetime.datetime.strptime(resp.StudyDate + resp.StudyTime, '%Y%m%d%H%M%S')
            exam_list.append(Exam(resp.StudyID, resp.PatientID, datetime_obj, self))
        exam_list = [exam for exam in exam_list if exam.datetime >= self.current_exam_datetime]
        return sorted(exam_list, key=lambda exam: exam.datetime)


class Exam(object):

    def __init__(self, id_, pat_id, datetime_, reaper):
        self.id_ = id_
        self.pat_id = pat_id
        self.datetime = datetime_
        self.reaper = reaper
        self.series_dict = {}

    def __str__(self):
        return 'Exam %s %s (%s)' % (self.id_, self.datetime, self.pat_id)

    def reap(self):
        """An exam must be reaped at least twice, since newly encountered series are not immediately reaped."""
        self.reaper.log.debug('Monitoring  %s' % self)
        updated_series_list = self.get_series_list() if self.pat_id.strip('/') not in reaper.discard_ids else []
        for updated_series in updated_series_list:
            if not self.reaper.alive: break
            if updated_series.id_ in self.series_dict:
                self.series_dict[updated_series.id_].reap(updated_series.image_count)
            else:
                self.reaper.log.info('New         %s' % updated_series)
                self.series_dict[updated_series.id_] = updated_series

    def get_series_list(self):
        responses = self.reaper.scu.find(scu.SeriesQuery(StudyID=self.id_))
        series_numbers = [int(resp.SeriesNumber) for resp in responses]
        uids = [resp.SeriesInstanceUID for resp in responses]
        image_counts = [int(resp.ImagesInAcquisition) for resp in responses]
        return [Series(self, self.reaper, id_, uid, image_cnt) for (id_, uid, image_cnt) in zip(series_numbers, uids, image_counts)]


class Series(object):

    def __init__(self, exam, reaper, id_, uid, image_count):
        self.exam = exam
        self.reaper = reaper
        self.id_ = id_
        self.uid = uid
        self.image_count = image_count
        self.needs_reaping = True

    def __str__(self):
        return '%s, Series %d, %d images' % (self.exam, self.id_, self.image_count)

    def reap(self, new_image_count):
        if new_image_count > self.image_count:
            self.image_count = new_image_count
            self.needs_reaping = True
            self.reaper.log.info('Monitoring  %s' % self)
        elif self.needs_reaping: # image count has stopped increasing
            self.reaper.log.info('Reaping     %s' % self)
            stage_dir = '%s_%s_%d_%s' % (self.reaper.id_, self.exam.id_, self.id_, datetime.datetime.now().strftime('%s'))
            reap_path = nimsutil.make_joined_path(self.reaper.reap_stage, stage_dir)
            reap_count = self.reaper.scu.move(scu.SeriesQuery(SeriesInstanceUID=self.uid), reap_path)
            if reap_count == self.image_count:
                self.tar_into_acquisitions(reap_path)
                shutil.move(reap_path, os.path.join(self.reaper.sort_stage, '.' + stage_dir))
                os.rename(os.path.join(self.reaper.sort_stage, '.' + stage_dir), os.path.join(self.reaper.sort_stage, stage_dir))
                self.needs_reaping = False
                self.reaper.log.info('Reaped      %s' % self)
            else:
                shutil.rmtree(reap_path)
                self.reaper.log.warning('Incomplete  %s, %d reaped' % (self, reap_count))

    def tar_into_acquisitions(self, series_path):
        dcm_dict = {}
        self.reaper.log.info('Compressing %s' % self)
        for filepath in [os.path.join(series_path, filename) for filename in os.listdir(series_path)]:
            dcm = dicom.read_file(filepath)
            acq_no = int(dcm.AcquisitionNumber) if 'AcquisitionNumber' in dcm else 0
            dcm_dict.setdefault(acq_no, []).append(filepath)
        for acq_no, acq_paths in dcm_dict.iteritems():
            arcdir_path = os.path.join(series_path, '%s_%d_%d' % (self.exam.id_, self.id_, acq_no))
            os.mkdir(arcdir_path)
            for filepath in acq_paths:
                os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, os.path.basename(filepath)))
            with tarfile.open('%s.tgz' % arcdir_path, 'w:gz', compresslevel=6) as archive:
                archive.add(arcdir_path, arcname=os.path.basename(arcdir_path))
            shutil.rmtree(arcdir_path)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('reap_path', help='path to reaping stage')
        self.add_argument('sort_path', help='path to sorting stage')
        self.add_argument('dicomserver', help='dicom server and port (hostname:port)')
        self.add_argument('aet', help='caller AE title')
        self.add_argument('aec', help='callee AE title')
        self.add_argument('-d', '--discard', default='discard', help='space-separated list of Patient IDs to discard')
        self.add_argument('-p', '--patid', help='glob for Patient IDs to reap (default: "*")')
        self.add_argument('-s', '--sleeptime', type=int, default=30, help='time to sleep before checking for new data')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    host, port, return_port = args.dicomserver.split(':')

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    scu_ = scu.SCU(host, port, return_port, args.aet, args.aec, log=log)
    datetime_file = os.path.join(os.path.dirname(__file__), '.%s.datetime' % args.aec)

    reaper = DicomReaper(args.aec, scu_, args.patid, args.discard.split(), args.reap_path, args.sort_path, datetime_file, args.sleeptime, log)

    def term_handler(signum, stack):
        reaper.halt()
        log.warning('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('Process halted')
