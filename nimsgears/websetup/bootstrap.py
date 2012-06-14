# -*- coding: utf-8 -*-
"""Set up the nimsgears application"""

from datetime import datetime

import logging
from tg import config
from nimsgears import model
import transaction

import nimsutil


superusers = [u'gsfr', u'bobd', u'rfbowen', u'laimab', u'nich0lsn', u'ltdet', u'kanile']

groups = [
        dict(gid=u'aetkin',     pis=[u'aetkin'],    managers=[u'kkpeng']),
        dict(gid=u'amnorcia',   pis=[u'amnorcia'],  managers=[u'jmales']),
        dict(gid=u'areiss1',    pis=[u'areiss1'],   managers=[u'maik']),
        dict(gid=u'awagner',    pis=[u'awagner'],   managers=[u'sfavila']),
        dict(gid=u'cni',        pis=[u'bobd'],      managers=[u'gsfr', u'rfbowen', u'laimab']),
        dict(gid=u'danls',      pis=[u'danls'],     managers=[u'jmtsang', u'hallinen']),
        dict(gid=u'gdaily',     pis=[u'gdaily'],    managers=[u'gbratman']),
        dict(gid=u'greicius',   pis=[u'greicius'],  managers=[u'lhua', u'heydee']),
        dict(gid=u'gross',      pis=[u'gross'],     managers=[u'kkalaf']),
        dict(gid=u'hallss',     pis=[u'hallss'],    managers=[u'hammond1', u'khustyi']),
        dict(gid=u'hardanay',   pis=[u'hardanay'],  managers=[u'acsamson']),
        dict(gid=u'henderj',    pis=[u'henderj'],   managers=[u'cindyc', u'gilja', u'cblabe']),
        dict(gid=u'hfeldman',   pis=[u'hfeldman'],  managers=[u'vndurand']),
        dict(gid=u'iang',       pis=[u'iang'],      managers=[u'arkadiy']),
        dict(gid=u'jparvizi',   pis=[u'jparvizi'],  managers=[u'vinitha']),
        dict(gid=u'kalanit',    pis=[u'kalanit'],   managers=[u'kweiner']),
        dict(gid=u'knutson',    pis=[u'knutson'],   managers=[u'kieferk']),
        dict(gid=u'llc',        pis=[u'llc'],       managers=[u'notthoff']),
        dict(gid=u'menon',      pis=[u'menon'],     managers=[u'sangs']),
        dict(gid=u'nass',       pis=[u'nass'],      managers=[u'lharbott']),
        dict(gid=u'ngolden',    pis=[u'ngolden'],   managers=[u'jenguyen']),
        dict(gid=u'pauly',      pis=[u'pauly'],     managers=[u'cvbowen', u'tjou']),
        dict(gid=u'smcclure',   pis=[u'smcclure'],  managers=[u'gstang', u'hennigan', u'mayas']),
        dict(gid=u'wandell',    pis=[u'wandell'],   managers=[u'lmperry']),
        dict(gid=u'unknown',    pis=[u'laimab'],    managers=[u'gsfr', u'rfbowen', u'bobd']),
        ]

access_privileges = [
        (0, u'ar', u'Anonymized Read'),
        (1, u'ro', u'Read-Only'),
        (2, u'rw', u'Read-Write'),
        (3, u'mg', u'Manage'),
        ]


def bootstrap(command, conf, vars):

    # <websetup.bootstrap.before.auth>

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

        print 'Bootstrapping research groups and members'
        for group in groups:
            g = model.ResearchGroup(gid=group['gid'])
            for uid in group['pis']:
                u = model.User.by_uid(uid=uid, create=True, password=uid)
                a.users.append(u)
                g.pis.append(u)
            for uid in group['managers']:
                u = model.User.by_uid(uid=uid, create=True, password=uid)
                a.users.append(u)
                g.managers.append(u)

        print 'Bootstrapping access privileges'
        for ap in access_privileges:
            model.AccessPrivilege(value=ap[0], name=ap[1], description=ap[2])

        print 'Bootstrapping @public user'
        u = model.User.by_uid(uid=u'@public', create=True, password=u'@public')
        u.name = u'Public Access'
        a.users.append(u)

        transaction.commit()

    except IntegrityError:
        import traceback
        print traceback.format_exc()
        transaction.abort()
        print 'ERROR: There was a problem during bootstrapping.'

    # <websetup.bootstrap.after.auth>
