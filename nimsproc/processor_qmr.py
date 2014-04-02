#!/usr/bin/env python

import sys
import time
import signal
import argparse
import sqlalchemy
import transaction
import subprocess
import shutil
import os.path
import logging
import platform
import getpass
import smtplib
from email.mime.text import MIMEText
import json
import tarfile

import nimsutil
from nimsgears.model import *

# PROCESSOR_CMD = 'matlab file.m'
PROCESSOR_CMD_CHECK = '/root/nims_qmr/nims_qmr_check'
PROCESSOR_CMD_COMPUTE = '/root/nims_qmr/nims_qmr_main'

SMTP_SERVER = 'smtp.stanford.edu'

log = logging.getLogger('processor-qmr')

class ProcessorWH(object):

    def __init__(self, db_uri, nims_path, task, filters, reset, sleeptime, tempdir):
        self.nims_path = nims_path
        self.task = unicode(task) if task else None
        self.filters = filters
        self.sleeptime = sleeptime
        self.tempdir = tempdir
        self.alive = True
        init_model(sqlalchemy.create_engine(db_uri))

        if reset: self.reset_all()

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            job = Job.query.join(DataContainer).join(Epoch) \
                .filter(Job.status==u'qmr-pending').order_by(Job.id).with_lockmode('update').first()

            if not job:
                time.sleep(self.sleeptime)
                continue

            job.status = u'qmr-process'

            epoch = job.data_container
            session = Session.query.get(epoch.session_datacontainer_id)

            jobs = Job.query.join(DataContainer).join(Epoch) \
                     .filter(Epoch.session_datacontainer_id == session.id).with_lockmode('update').all()
            epochs = session.epochs

            subject = Subject.query.join(Experiment, Subject.experiment_datacontainer_id == Experiment.datacontainer_id) \
                            .filter(Subject.datacontainer_id == session.subject_datacontainer_id).first()

            group_users = []

            research_group = subject.experiment.owner
            group_users = [user.uid for user in set(research_group.members + research_group.managers)]

            group = subject.experiment.owner.gid
            experiment = str(subject.experiment.name)
            sessionID = session.name

            # make sure all epochs have been processed (niftis exist)
            all_epochs_have_nifti = True
            for e in epochs:
                if not any(ds for ds in e.datasets if ds.filetype == 'nifti'):
                    all_epochs_have_nifti = False
                    break

            if not all_epochs_have_nifti:
                log.info("There is one or more Epochs missing niftis")
                transaction.commit()
                continue

            # Get the user who made the upload
            ds = job.data_container.primary_dataset
            dcm_tgz = os.path.join(self.nims_path, ds.relpath, os.listdir(os.path.join(self.nims_path, ds.relpath))[0])
            with tarfile.open(dcm_tgz) as archive:
                for tarinfo in archive:
                    if tarinfo.name.endswith('.json'):
                        # Parse json and extract the user id
                        info = json.load(archive.extractfile(tarinfo))
                        break

            user = info['User']

            # Run the script
            res = subprocess.call( [PROCESSOR_CMD_CHECK,
                                     group,
                                     experiment,
                                     sessionID] )
            if res == 0:
                log.error('Error running QMR processor')
                # Mark the processing as failed
                for j in jobs:
                    j.status = u'failed'
                    j.activity = 'Failed to run QMR Matlab check'

                transaction.commit()
                continue
            elif res == 111:
                log.info("Sending notification process started for job: %d and user: %s" % (job.id, user))
                content = '''

                    Message to user in processor_qmr
                    Process is starting now.

                '''
                self.send_mail(user, 'Started QMR processing on job %d' % job.id, content)

                # nims_qmr_main -g group -e experiment -s session -u "user list"
                res2 = subprocess.call( [PROCESSOR_CMD_COMPUTE,
                                        '-g', group,
                                        '-e', experiment,
                                        '-s', sessionID,
                                        '-u', ' '.join(group_users)] )
                if res2 == 0:
                    log.error('Error running Matlab')
                    for j in jobs:
                        j.status = u'failed'
                        j.activity = 'Failed to run QMR Matlab process'
                    transaction.commit()
                    continue

                elif res2 == 999:
                    log.error('System Error')
                    for j in jobs:
                        j.status = u'failed'
                        j.activity = 'Failed to run QMR Matlab process'
                    transaction.commit()
                    continue

                elif res2 == 111:
                    log.info("Sending success mail job: %d and user: %s" % (job.id, user))
                    content = '''

                        Message to user in processor_qmr
                        Process succesfully completed.

                    '''
                    self.send_mail(user, 'Finished QMR processing on job %d' % job.id, content)

                else:
                    log.error('Cannot process QMR return code: %d' % res2)
                    transaction.commit()
                    continue

            else:
                log.info('Check later, not enough NIfTIs')
                transaction.commit()
                continue

            # Mark all the qmr-pending jobs as done
            for j in jobs:
                j.status = u'done'
                j.activity = 'done'

            transaction.commit()

    def send_mail(self, user, subject, body):
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = getpass.getuser() + '@' + platform.node()
        msg['To'] = user + '@stanford.edu'

        server = smtplib.SMTP(SMTP_SERVER)
        server.starttls()

        server.sendmail(msg['From'], [msg['To']], msg.as_string())
        server.quit()


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', metavar='URI', help='database URI')
        self.add_argument('nims_path', metavar='DATA_PATH', help='data location')
        self.add_argument('-T', '--task', help='find|proc  (default is all)')
        self.add_argument('-e', '--filter', default=[], action='append', help='sqlalchemy filter expression')
        # self.add_argument('-j', '--jobs', type=int, default=1, help='maximum number of concurrent threads')
        # self.add_argument('-k', '--reconjobs', type=int, default=8, help='maximum number of concurrent recon jobs')
        self.add_argument('-r', '--reset', action='store_true', help='reset currently active (crashed) jobs')
        self.add_argument('-s', '--sleeptime', type=int, default=10, help='time to sleep between db queries')
        self.add_argument('-t', '--tempdir', help='directory to use for temporary files')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='log level (default: info)')
        self.add_argument('-q', '--quiet', action='store_true', default=False, help='disable console logging')


if __name__ == '__main__':
    # workaround for http://bugs.python.org/issue7980
    import datetime # used in nimsutil
    datetime.datetime.strptime('0', '%S')

    args = ArgumentParser().parse_args()
    nimsutil.configure_log(args.logfile, not args.quiet, args.loglevel)
    processor = ProcessorWH(args.db_uri, args.nims_path, args.task,
                        args.filter, args.reset, args.sleeptime, args.tempdir)

    def term_handler(signum, stack):
        processor.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    processor.run()
    log.warning('Process halted')

