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

import nimsutil
from nimsgears.model import *

# PROCESSOR_CMD = 'matlab file.m'
PROCESSOR_CMD_CHECK = '/Users/sbenito/test_wh.sh'
#PROCESSOR_CMD_CHECK = '/root/nims_qmr/nims_qmr_get_exit_code'
#PROCESSOR_CMD_COMPUTE = '/root/nims_qmr/nims_qmr_main'

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

            job.status = 'qmr-process'

            epoch = job.data_container
            session = Session.query.get(epoch.session_datacontainer_id)

            jobs = Job.query.join(DataContainer).join(Epoch) \
                     .filter(Epoch.session_datacontainer_id==session.id).with_lockmode('update').all()
            epochs = session.epochs

            subject = Subject.query.join(Experiment, Subject.experiment_datacontainer_id == Experiment.datacontainer_id) \
                            .filter(Subject.datacontainer_id == session.subject_datacontainer_id).first()

            group_users = []

            for user_experiment in subject.experiment.accesses:
                # user_experiment is expected to be a string like:
                # 'access-type: (user, manager/experiment)'
                # and we need to extract the user
                user = user_experiment.split()[1][1:-1]
                group_users.append(user)
                # sunetID_begining = str(elem).index('(') + 1
                #sunetID_end = str(elem).index(',')
                # group_users.append(str(elem)[sunetID_begining: sunetID_end])

            print group_users

            #nimsfs_niftis_path = '%s-%s-%s-%s' % (subject.experiment.owner.gid, str(subject.experiment.name), session.name, group_users)
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

            # Run the script
            res = subprocess.call( [PROCESSOR_CMD_CHECK, group, experiment] )
            if res == 0:
                log.error('Error running QMR processor')
                # Mark the processing as failed
                for j in jobs:
                    j.status = u'failed'
                    j.activity = 'Failed to run QMR matlab processsing'

                transaction.commit()
                continue
            elif res == 222:
                res2 = subprocess.call( [PROCESSOR_CMD_COMPUTE, group, experiment, sessionID, ','.join(group_users)] )

            else:
                log.info('Check later, not enough NIfTIs')
                transaction.commit()
                continue

            # Mark all the qmr-pending jobs as done
            for j in jobs:
                j.status = u'done'
                j.activity = 'done'

            transaction.commit()


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

