# @author:  Gunnar Schaefer

from datetime import datetime

import logging
from tg import config
from nimsgears import model
import transaction

import nimsutil


superusers = [
        ]

groups = [
        dict(gid=u'unknown',    pis=[],             managers=[]),
        ]


def bootstrap(command, conf, vars):

    # <websetup.bootstrap.before.auth>

    from sqlalchemy.exc import IntegrityError

    try:
        s = model.Group(gid=u'superusers', name=u'Superusers')
        a = model.Group(gid=u'users', name=u'Users')

        # TODO: a new user should automatically get a u'Welcome to NIMS' message

        print 'Bootstrapping superusers'
        for uid in superusers:
            u = model.User.by_uid(uid=uid, create=True)
            s.users.append(u)
            a.users.append(u)

        print 'Bootstrapping research groups and members'
        for group in groups:
            g = model.ResearchGroup(gid=group['gid'])
            for uid in group['pis']:
                u = model.User.by_uid(uid=uid, create=True)
                a.users.append(u)
                g.pis.append(u)
            for uid in group['managers']:
                u = model.User.by_uid(uid=uid, create=True)
                a.users.append(u)
                g.managers.append(u)

        print 'Bootstrapping @public user'
        u = model.User.by_uid(uid=u'@public', create=True)
        u.lastname = u'Public Access'
        a.users.append(u)

        transaction.commit()

    except IntegrityError:
        import traceback
        print traceback.format_exc()
        transaction.abort()
        print 'ERROR: There was a problem during bootstrapping.'

    # <websetup.bootstrap.after.auth>
