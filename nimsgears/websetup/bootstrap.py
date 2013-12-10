# @author:  Gunnar Schaefer

from datetime import datetime

import logging
from tg import config
from nimsgears import model
import transaction

import nimsutil


superusers = [
        u'gsfr',
        u'bobd',
        u'rfbowen',
        u'laimab',
        u'sbenito',
        ]

groups = [
        dict(gid=u'unknown',    pis=[],             managers=[u'laimab']),
        dict(gid=u'geservice',  pis=[u'bobd'],      managers=[u'gsfr', u'laimab']),
        dict(gid=u'aetkin',     pis=[u'aetkin'],    managers=[u'kkpeng']),
        dict(gid=u'amnorcia',   pis=[u'amnorcia'],  managers=[u'jmales']),
        dict(gid=u'areiss1',    pis=[u'areiss1'],   managers=[u'maik']),
        dict(gid=u'awagner',    pis=[u'awagner'],   managers=[u'sfavila']),
        dict(gid=u'cni',        pis=[u'bobd'],      managers=[u'gsfr', u'laimab']),
        dict(gid=u'danls',      pis=[u'danls'],     managers=[u'jmtsang', u'hallinen']),
        dict(gid=u'fbaker',     pis=[u'fbaker'],    managers=[u'nzahr']),
        dict(gid=u'gdaily',     pis=[u'gdaily'],    managers=[u'gbratman']),
        dict(gid=u'greicius',   pis=[u'greicius'],  managers=[u'lhua', u'heydee']),
        dict(gid=u'gross',      pis=[u'gross'],     managers=[u'kkalaf']),
        dict(gid=u'hallss',     pis=[u'hallss'],    managers=[u'khustyi']),
        dict(gid=u'hardanay',   pis=[u'hardanay'],  managers=[u'acsamson']),
        dict(gid=u'henderj',    pis=[u'henderj'],   managers=[u'cindyc', u'gilja', u'cblabe']),
        dict(gid=u'hfeldman',   pis=[u'hfeldman'],  managers=[u'vndurand']),
        dict(gid=u'iang',       pis=[u'iang'],      managers=[u'mlhenry']),
        dict(gid=u'jparvizi',   pis=[u'jparvizi'],  managers=[u'vinitha']),
        dict(gid=u'jzaki',      pis=[u'jzaki'],     managers=[u'enook']),
        dict(gid=u'kalanit',    pis=[u'kalanit'],   managers=[u'kweiner']),
        dict(gid=u'klposton',   pis=[u'klposton'],  managers=[u'sophiey']),
        dict(gid=u'knutson',    pis=[u'knutson'],   managers=[u'kieferk']),
        dict(gid=u'lisaac',     pis=[u'lisaac'],    managers=[]),
        dict(gid=u'llc',        pis=[u'llc'],       managers=[u'notthoff']),
        dict(gid=u'menon',      pis=[u'menon'],     managers=[u'sangs']),
        dict(gid=u'nambady',    pis=[u'nambady'],   managers=[u'blhughes']),
        dict(gid=u'nass',       pis=[u'nass'],      managers=[u'lharbott']),
        dict(gid=u'ngolden',    pis=[u'ngolden'],   managers=[u'jenguyen']),
        dict(gid=u'nordahl',    pis=[u'crswu'],     managers=[u'rtjohn']),
        dict(gid=u'pauly',      pis=[u'pauly'],     managers=[u'cvbowen', u'tjou']),
        dict(gid=u'smcclure',   pis=[u'smcclure'],  managers=[u'gstang', u'hennigan', u'mayas']),
        dict(gid=u'wandell',    pis=[u'wandell'],   managers=[u'lmperry']),
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
