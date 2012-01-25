#!/usr/bin/env python
#
# @author:  Gunnar Schaefer
#           Reno Bowen

import os
import sys
import time
import shutil
import signal
import argparse
import datetime
import collections

import scu
import nimsutil


class DicomReaper(object):

    def __init__(self, id_, scu, reap_stage, sort_stage, datetime_file, sleep_time, log):
        self.id_ = id_
        self.scu = scu
        self.reap_stage = reap_stage
        self.sort_stage = sort_stage
        self.datetime_file = datetime_file
        self.sleep_time = sleep_time
        self.log = log

        self.current_exam_datetime = nimsutil.get_reference_datetime(self.datetime_file)
        self.monitored_exams = collections.deque()
        self.alive = True

        # stage any files left behind from a previous run
        for item in os.listdir(self.reap_stage):
            if item.startswith(self.id_):
                os.rename(os.path.join(self.reap_stage, item), os.path.join(self.sort_stage, item))

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            outstanding_exams = self.get_outstanding_exams()
            n_monitored_exams = len(self.monitored_exams)
            n_outstanding_exams = len(outstanding_exams)

            if n_monitored_exams and n_outstanding_exams and self.monitored_exams[0].id_ != outstanding_exams[0].id_:
                vanished_exam = self.monitored_exams.popleft()
                n_monitored_exams = len(self.monitored_exams)
                self.log.warning('Dropping %s (assumed deleted from scanner)' % vanished_exam)

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
                self.log.info('New     %s' % self.monitored_exams[-1])

            for exam in self.monitored_exams:
                if not self.alive: return
                exam.reap()

            time.sleep(self.sleep_time)

    def get_outstanding_exams(self):
        date = self.current_exam_datetime.strftime('%Y%m%d-')
        response_list = self.scu.find(scu.StudyQuery(StudyDate=date))
        exam_list = []
        for resp in response_list:
            exam_id = resp.StudyID
            datetime_str = resp.StudyDate + resp.StudyTime
            datetime_obj = datetime.datetime.strptime(datetime_str, '%Y%m%d%H%M%S')
            exam_list.append(Exam(exam_id, datetime_obj, self))
        exam_list = [exam for exam in exam_list if exam.datetime >= self.current_exam_datetime]
        return sorted(exam_list, key=lambda exam: exam.datetime)


class Exam(object):

    def __init__(self, id_, datetime_, reaper):
        self.id_ = id_
        self.datetime = datetime_
        self.reaper = reaper
        self.series_dict = {}

    def __repr__(self):
        return 'Exam<%s %s>' % (self.id_, self.datetime)

    def reap(self):
        """An exam must be reaped at least twice, since newly encountered series are not immediately reaped."""
        reaper.log.debug('Monitoring %s' % self)
        updated_series_list = self.get_series_list()
        for updated_series in updated_series_list:
            if not self.reaper.alive: break
            if updated_series.id_ in self.series_dict:
                self.series_dict[updated_series.id_].reap(updated_series.image_count)
            else:
                reaper.log.info('New     %s' % updated_series)
                self.series_dict[updated_series.id_] = updated_series

    def get_series_list(self):
        responses = reaper.scu.find(scu.SeriesQuery(StudyID=self.id_))
        series_numbers = [int(resp.SeriesNumber) for resp in responses]
        image_counts = [int(resp.ImagesInAcquisition) for resp in responses]
        return [Series(self, self.reaper, id_, image_cnt) for (id_, image_cnt) in zip(series_numbers, image_counts)]


class Series(object):

    def __init__(self, exam, reaper, id_, image_count):
        self.exam = exam
        self.reaper = reaper
        self.id_ = id_
        self.image_count = image_count
        self.needs_reaping = True

    def __repr__(self):
        return 'Series<%s, id=%d, img_cnt=%d>' % (self.exam, self.id_, self.image_count)

    def reap(self, new_image_count):
        if new_image_count > self.image_count:
            self.image_count = new_image_count
            self.needs_reaping = True
            self.reaper.log.info('Monitoring %s' % self)
        elif self.needs_reaping: # image count has stopped increasing
            self.reaper.log.info('Reaping %s' % self)
            now = datetime.datetime.now().strftime('%s')
            stage_dir = '%s_%s-%d_%s' % (self.reaper.id_, self.exam.id_, self.id_, now)
            reap_path = nimsutil.make_joined_path(self.reaper.reap_stage, stage_dir)
            reap_count = self.reaper.scu.move(scu.SeriesQuery(StudyID=self.exam.id_, SeriesNumber=self.id_), reap_path)
            if reap_count >= self.image_count:
                self.needs_reaping = False
                shutil.move(reap_path, reaper.sort_stage)
                self.reaper.log.info('Reaped  %s' % self)
            else:
                shutil.rmtree(reap_path)
                self.reaper.log.warning('Reaped incomplete %s, reap_cnt=%d' % (self, reap_count))


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.configure()

    def configure(self):
        self.add_argument('stage_path', help='path to staging area')
        self.add_argument('dicomserver', help='dicom server and port (hostname:port)')
        self.add_argument('aet', help='caller AE title')
        self.add_argument('aec', help='callee AE title')
        self.add_argument('sleep_time', type=int, help='time to sleep before checking for new data')
        self.add_argument('-n', '--logname', default=__file__, help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')

    def error(self, message):
        self.print_help()
        sys.exit(1)


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    host, port = args.dicomserver.split(':')

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    scu_ = scu.SCU(host, port, args.aet, args.aec, log=log)
    reap_stage = nimsutil.make_joined_path(args.stage_path, 'reap')
    sort_stage = nimsutil.make_joined_path(args.stage_path, 'sort')
    datetime_file = '.%s.datetime' % host

    reaper = DicomReaper(host, scu_, reap_stage, sort_stage, datetime_file, args.sleep_time, log)

    def term_handler(signum, stack):
        reaper.halt()
        log.warning('Received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('Process halted')
