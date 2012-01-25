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
        dict(id=u'aetkin',   pis=[u'aetkin'],   admins=[]),
        dict(id=u'amnorcia', pis=[u'amnorcia'], admins=[]),
        dict(id=u'areiss1',  pis=[u'areiss1'],  admins=[u'maik']),
        dict(id=u'awagner',  pis=[u'awagner'],  admins=[]),
        dict(id=u'cni',      pis=[], admins=[]), # FIXME: dict(name=u'cni', pis=[u'bobd'], admins=[]),
        dict(id=u'danls',    pis=[u'danls'],    admins=[u'danls_mg1', u'danls_mg2']),
        dict(id=u'greicius', pis=[u'greicius'], admins=[]),
        dict(id=u'gross',    pis=[u'gross'],    admins=[u'kkalaf']),
        dict(id=u'hallss',   pis=[u'hallss'],   admins=[]),
        dict(id=u'hardanay', pis=[u'hardanay'], admins=[]),
        dict(id=u'henderj',  pis=[u'henderj'],  admins=[]),
        dict(id=u'hfeldman', pis=[u'hfeldman'], admins=[]),
        dict(id=u'iang',     pis=[u'iang'],     admins=[]),
        dict(id=u'jparvizi', pis=[u'jparvizi'], admins=[u'jparvizi_mg1', u'jparvizi_mg2']),
        dict(id=u'kalanit',  pis=[u'kalanit'],  admins=[]),
        dict(id=u'knutson',  pis=[u'knutson'],  admins=[u'knutson_mg1', u'knutson_mg2']),
        dict(id=u'llc',      pis=[u'llc'],      admins=[]),
        dict(id=u'menon',    pis=[u'menon'],    admins=[]),
        dict(id=u'pauly',    pis=[u'pauly'],    admins=[]),
        dict(id=u'qa',       pis=[u'laimab'],   admins=[]),
        dict(id=u'sapolsky', pis=[u'sapolsky'], admins=[]),
        dict(id=u'smcclure', pis=[u'smcclure'], admins=[]),
        dict(id=u'wandell',  pis=[u'wandell'],  admins=[u'lmperry']),
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
        s.id = u'superusers'
        s.name = u'Superusers'

        a = model.Group()
        a.id = u'users'
        a.name = u'Users'

        # FIXME: don't create two users for the same name
        # TODO: a new user should automatically get a u'Welcome to NIMS' message

        print 'Bootstrapping superusers'
        for id_ in superusers:
            u = model.User(id=id_, password=id_)
            s.users.append(u)
            a.users.append(u)

        print 'Bootstrapping research groups'
        for group in groups:
            g = model.ResearchGroup(id=group['id'])
            for id_ in group['pis']:
                u = model.User(id=id_, password=id_)
                a.users.append(u)
                g.pis.append(u)
            for id_ in group['admins']:
                u = model.User(id=id_, password=id_)
                a.users.append(u)
                g.admins.append(u)

        print 'Bootstrapping access privileges'
        for ap in access_privileges:
            model.AccessPrivilege(value=ap[0], name=ap[1], description=ap[2])

        transaction.commit()

        print 'Trying to update user info via LDAP'
        for user in model.User.query.all():
            ldap_name, ldap_email = nimsutil.ldap_query(user.id)
            user.name = ldap_name
            user.email = ldap_email

        transaction.commit()

    except IntegrityError:
        import traceback
        print traceback.format_exc()
        transaction.abort()
        print 'ERROR: There was a problem during bootstrapping.'

    # <websetup.bootstrap.after.auth>
