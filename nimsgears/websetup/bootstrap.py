# -*- coding: utf-8 -*-
"""Set up the nimsgears application"""

from datetime import datetime

import logging
from tg import config
from nimsgears import model
import transaction

import nimsutil


superusers = [u'gsfr', u'bobd', u'rfbowen']

groups = [
        dict(gid=u'aetkin',     pis=[u'aetkin'],    admins=[]),
        dict(gid=u'amnorcia',   pis=[u'amnorcia'],  admins=[]),
        dict(gid=u'areiss1',    pis=[u'areiss1'],   admins=[u'maik']),
        dict(gid=u'awagner',    pis=[u'awagner'],   admins=[]),
        dict(gid=u'cni',        pis=[u'bobd'],      admins=[u'gsfr', u'rfbowen']),
        dict(gid=u'danls',      pis=[u'danls'],     admins=[u'danls_mg1', u'danls_mg2']),
        dict(gid=u'gdaily',     pis=[u'gdaily'],    admins=[]),
        dict(gid=u'greicius',   pis=[u'greicius'],  admins=[]),
        dict(gid=u'gross',      pis=[u'gross'],     admins=[u'kkalaf']),
        dict(gid=u'hallss',     pis=[u'hallss'],    admins=[]),
        dict(gid=u'hardanay',   pis=[u'hardanay'],  admins=[]),
        dict(gid=u'henderj',    pis=[u'henderj'],   admins=[]),
        dict(gid=u'hfeldman',   pis=[u'hfeldman'],  admins=[]),
        dict(gid=u'iang',       pis=[u'iang'],      admins=[]),
        dict(gid=u'jparvizi',   pis=[u'jparvizi'],  admins=[u'jparvizi_mg1', u'jparvizi_mg2']),
        dict(gid=u'kalanit',    pis=[u'kalanit'],   admins=[]),
        dict(gid=u'knutson',    pis=[u'knutson'],   admins=[u'knutson_mg1', u'knutson_mg2']),
        dict(gid=u'llc',        pis=[u'llc'],       admins=[]),
        dict(gid=u'menon',      pis=[u'menon'],     admins=[]),
        dict(gid=u'pauly',      pis=[u'pauly'],     admins=[]),
        dict(gid=u'qa',         pis=[u'laimab'],    admins=[]),
        dict(gid=u'sapolsky',   pis=[u'sapolsky'],  admins=[]),
        dict(gid=u'smcclure',   pis=[u'smcclure'],  admins=[]),
        dict(gid=u'wandell',    pis=[u'wandell'],   admins=[u'lmperry']),
        dict(gid=u'unknown',    pis=[],             admins=[]),
        ]

access_privileges = [
        (0, u'ar', u'anonymized read'),
        (1, u'ro', u'read-only'),
        (2, u'rw', u'read-write'),
        (3, u'mg', u'manage'),
        ]


def bootstrap(command, conf, vars):

    # <websetup.bootstrap.before.auth

    from sqlalchemy.exc import IntegrityError

    try:
        s = model.Group()
        s.gid = u'superusers'
        s.name = u'Superusers'

        a = model.Group()
        a.gid = u'users'
        a.name = u'Users'

        # TODO: a new user should automatically get a u'Welcome to NIMS' message

        print 'Bootstrapping superusers'
        for uid in superusers:
            u = model.User.by_uid(uid=uid, create=True, password=uid)
            s.users.append(u)
            a.users.append(u)

        print 'Bootstrapping research groups'
        for group in groups:
            g = model.ResearchGroup(gid=group['gid'])
            for uid in group['pis']:
                u = model.User.by_uid(uid=uid, create=True, password=uid)
                a.users.append(u)
                g.pis.append(u)
            for uid in group['admins']:
                u = model.User.by_uid(uid=uid, create=True, password=uid)
                a.users.append(u)
                g.admins.append(u)

        print 'Bootstrapping access privileges'
        for ap in access_privileges:
            model.AccessPrivilege(value=ap[0], name=ap[1], description=ap[2])

        transaction.commit()

    except IntegrityError:
        import traceback
        print traceback.format_exc()
        transaction.abort()
        print 'ERROR: There was a problem during bootstrapping.'

    # <websetup.bootstrap.after.auth>
