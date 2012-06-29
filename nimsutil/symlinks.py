#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import sys
import shlex
import shutil
import argparse
import tempfile
import subprocess

import sqlalchemy

from nimsgears.model import *


class SymLinker(object):

    def __init__(self, db_uri, nims_path):
        super(SymLinker, self).__init__()
        self.nims_path = nims_path
        init_model(sqlalchemy.create_engine(db_uri))

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
            with open(os.path.join(user_path, '.htaccess'), 'w') as htaccess:
                htaccess.write('AuthType WebAuth\n')
                htaccess.write('Require user %s\n' % uid)

        superuser_path = os.path.join(links_path, 'superuser')
        os.mkdir(superuser_path)
        with open(os.path.join(superuser_path, '.htaccess'), 'w') as htaccess:
            htaccess.write('AuthType WebAuth\n')
            for superuser in User.query.join(Group, User.groups).filter(Group.gid == u'superusers').all():
                htaccess.write('Require user %s\n' % superuser.uid)

        epoch_paths = []
        symlinks = []
        for r in db_results:
            user_path = os.path.join(links_path, r.User.uid)
            ep = '%s/%s/%s/%s/%s' % (user_path, r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name)
            su_ep = '%s/%s/%s/%s/%s' % (superuser_path, r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name)
            sl = (os.path.join(self.nims_path, r.Dataset.relpath), os.path.join(ep, r.Dataset.name))
            su_sl = (os.path.join(self.nims_path, r.Dataset.relpath), os.path.join(su_ep, r.Dataset.name))
            epoch_paths.extend([ep, su_ep])
            symlinks.extend([sl, su_sl])

        for ep in set(epoch_paths):
            os.makedirs(ep)
        for sl in set(symlinks):
            os.symlink(*sl)


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('-f', '--forever', action='store_true', help='run forever, implies -t')
        self.add_argument('-t', '--tempdir', action='store_true', help='create links in temp dir and rsync to links_path')
        self.add_argument('db_uri', help='database URI')
        self.add_argument('nims_path', help='absolute path to data')
        self.add_argument('links_path', help='absolute path to links')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    args.tempdir = args.forever or args.tempdir

    if not os.path.isdir(args.links_path) or (not args.tempdir and os.listdir(args.links_path)):
        print '`links_path` must exist and be an empty directory'
        sys.exit(1)

    linker = SymLinker(args.db_uri, args.nims_path)
    while True:
        import datetime
        start_time = datetime.datetime.now()

        tmp_links_path = tempfile.mkdtemp()
        try:
            linker.make_links(tmp_links_path)
            if args.tempdir:
                subprocess.call(shlex.split('rsync -a --del %s/ %s' % (tmp_links_path, args.links_path)))
            else:
                for dir_item in os.listdir(tmp_links_path):
                    shutil.move(os.path.join(tmp_links_path, dir_item), args.links_path)
        except KeyboardInterrupt:
            sys.exit(0)
        finally:
            shutil.rmtree(tmp_links_path)
        if not args.forever:
            break

        print datetime.datetime.now() - start_time
