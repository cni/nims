#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import os
import argparse

import sqlalchemy

from nimsgears.model import *


class SymLinker(object):

    def __init__(self, db_uri, nims_path, links_path):
        super(SymLinker, self).__init__()
        self.nims_path = nims_path
        self.links_path = links_path
        init_model(sqlalchemy.create_engine(db_uri))

    def make_links(self):
        db_results = (DBSession.query(Dataset, Epoch, Session, Experiment, ResearchGroup, User)
                .join(Epoch, Dataset.container)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .join(Access)
                .join(User, Access.user)
                .all())

        #db_results = (DBSession.query(User, ResearchGroup, Experiment, Session, Epoch, Dataset)
        #        .join(Access, User.accesses)
        #        .join(Experiment, Access.experiment)
        #        .join(Subject, Experiment.subjects)
        #        .join(Session, Subject.sessions)
        #        .join(Epoch, Session.epochs)
        #        .join(Dataset, Epoch.datasets)
        #        .join(ResearchGroup)
        #        .all())

        with open(os.path.join(self.links_path, '.htaccess'), 'w') as htaccess:
            htaccess.write('AuthType WebAuth\n')
            htaccess.write('Require valid-user\n')

        for uid in set(r.User.uid for r in db_results):
            user_path = os.path.join(self.links_path, uid)
            os.mkdir(user_path)
            with open(os.path.join(user_path, '.htaccess'), 'w') as htaccess:
                htaccess.write('AuthType WebAuth\n')
                htaccess.write('Require user %s\n' % uid)

        superuser_path = os.path.join(self.links_path, 'superuser')
        os.mkdir(superuser_path)
        with open(os.path.join(superuser_path, '.htaccess'), 'w') as htaccess:
            htaccess.write('AuthType WebAuth\n')
            for superuser in User.query.join(Group, User.groups).filter(Group.gid == u'superusers').all():
                htaccess.write('Require user %s\n' % superuser.uid)

        epoch_paths = []
        symlinks = []
        for r in db_results:
            user_path = os.path.join(self.links_path, r.User.uid)
            ep = '%s/%s/%s/%s/%s' % (user_path, r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name)
            su_ep = '%s/%s/%s/%s/%s' % (superuser_path, r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name)
            sl = (os.path.join(self.nims_path, r.Dataset.relpath), os.path.join(ep, r.Dataset.name))
            su_sl = (os.path.join(self.nims_path, r.Dataset.relpath), os.path.join(su_ep, r.Dataset.name))
            epoch_paths.extend([ep, su_ep])
            symlinks.extend([sl, su_sl])

        for ep in set(epoch_paths):
            os.makedirs(ep)
        for sl in set(symlinks):
            try:
                os.symlink(*sl)
            except OSError:
                print sl


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.add_argument('db_uri', help='database URI')
        self.add_argument('nims_path', help='data location')
        self.add_argument('links_path', help='links location')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    SymLinker(args.db_uri, args.nims_path, args.links_path).make_links()

