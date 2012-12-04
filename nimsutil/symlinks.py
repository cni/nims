#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import time
import shlex
import shutil
import argparse
import tempfile
import subprocess

import sqlalchemy

import nimsutil
from nimsgears.model import *


class SymLinker(object):

    def __init__(self, db_uri, nims_path):
        super(SymLinker, self).__init__()
        self.nims_path = nims_path
        init_model(sqlalchemy.create_engine(db_uri, echo=False))

    def make_links(self, links_path):
        db_results = (DBSession.query(Dataset, Epoch, Session, Experiment, ResearchGroup, User)
                .join(Epoch, Dataset.container)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .join(Access)
                .join(User, Access.user)
                .all())

        with open(os.path.join(links_path, '.htaccess'), 'w') as htaccess:
            htaccess.write('AuthType WebAuth\n')
            htaccess.write('Require valid-user\n')

        for uid in set(r.User.uid for r in db_results):
            user_path = os.path.join(links_path, uid)
            os.mkdir(user_path)
            shutil.copy(os.path.join(os.path.dirname(__file__), 'download.php'), user_path)
            with open(os.path.join(user_path, '.htaccess'), 'w') as htaccess:
                htaccess.write('AuthType WebAuth\n')
                htaccess.write('Require user %s\n' % uid)

        superuser_path = os.path.join(links_path, 'superuser')
        os.mkdir(superuser_path)
        shutil.copy(os.path.join(os.path.dirname(__file__), 'download.php'), superuser_path)
        with open(os.path.join(superuser_path, '.htaccess'), 'w') as htaccess:
            htaccess.write('AuthType WebAuth\n')
            for superuser in User.query.join(Group, User.groups).filter(Group.gid == u'superusers').all():
                htaccess.write('Require user %s\n' % superuser.uid)

        epoch_paths = []
        symlinks = []
        for r in db_results:
            user_path = os.path.join(links_path, r.User.uid)
            ep = '%s/nims/%s/%s/%s/%s' % (user_path, r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name)
            su_ep = '%s/nims/%s/%s/%s/%s' % (superuser_path, r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name)
            sl = (os.path.join(self.nims_path, r.Dataset.relpath), os.path.join(ep, r.Dataset.name))
            su_sl = (os.path.join(self.nims_path, r.Dataset.relpath), os.path.join(su_ep, r.Dataset.name))
            epoch_paths.extend([ep, su_ep])
            symlinks.extend([sl, su_sl])

        for ep in set(epoch_paths):
            os.makedirs(ep)
        for sl in set(symlinks):    # set() removes superuser symlink duplicates
            os.symlink(*sl)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('-c', '--continuous', action='store_true', help='run continuously, implies -i')
        self.add_argument('-i', '--inplace', action='store_true', help='update existing links_path with rsync')
        self.add_argument('-t', '--interval', type=int, default=300, help='total interval per iteration (default: 300s)')
        self.add_argument('-n', '--logname', default=os.path.splitext(os.path.basename(__file__))[0], help='process name for log')
        self.add_argument('-f', '--logfile', help='path to log file')
        self.add_argument('-l', '--loglevel', default='info', help='path to log file')
        self.add_argument('db_uri', help='database URI')
        self.add_argument('nims_path', help='absolute path to data')
        self.add_argument('links_path', help='links will be in links_path/nimslinks')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    args.inplace = args.continuous or args.inplace

    if not os.path.isdir(args.links_path) or not os.access(args.links_path, os.W_OK):
        print 'ERROR: %s must exist and be a writable directory' % args.links_path
        sys.exit(1)

    nims_links_path = os.path.join(args.links_path, 'nimslinks')

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)
    linker = SymLinker(args.db_uri, args.nims_path)
    while True:
        start_time = time.time()
        tmp_links_path = tempfile.mkdtemp(dir=args.links_path)
        try:
            linker.make_links(tmp_links_path)
            os.chmod(tmp_links_path, 0o755)
            if args.inplace:
                subprocess.call(shlex.split('rsync -a --del %s/ %s' % (tmp_links_path, nims_links_path)))
            else:
                shutil.rmtree(nims_links_path, ignore_errors=True)
                shutil.move(tmp_links_path, nims_links_path)
        except KeyboardInterrupt:
            sys.exit(0)
        finally:
            shutil.rmtree(tmp_links_path, ignore_errors=True)

        log.info('runtime: %.1fs' % (time.time() - start_time))
        if not args.continuous:
            break

        time.sleep(args.interval - time.time() + start_time)
