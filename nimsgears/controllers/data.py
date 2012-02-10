# -*- coding: utf-8 -*-
"""Sample controller with all its actions protected."""
from tg import config, expose, flash, redirect, request, require
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates
from tgext.admin.controller import AdminController
from tgext.admin.tgadminconfig import TGAdminConfig

from collections import OrderedDict

from nimsgears import model
from nimsgears.model import *

from nimsgears.lib.base import BaseController

import nimsutil

__all__ = ['DataController', 'PublicDataController']


class NimsAdminConfig(TGAdminConfig):
    default_index_template = 'genshi:nimsgears.templates.tg_admin'


class NimsAdminController(AdminController):
    allow_only = predicates.in_group('superusers')


class DataController(BaseController):

    @expose()
    def index(self):
        redirect('/pub/browse')

    @expose()
    def browse(self, **kwargs):
        return dict(page='browse')

class AuthDataController(DataController):

    tg_admin = NimsAdminController(model, DBSession, NimsAdminConfig)

    allow_only = predicates.not_anonymous(msg=l_('You must be logged in to view this page.'))

    # FIXME: handle deactivated users
    #active_user = predicates.in_group('users', msg=l_('Your account is inactive. You can request activation below.'))

    def _not_active_user(msg):
        flash(msg)
        redirect('/auth/activate')

    @expose()
    def index(self):
        redirect('/auth/status')

    @expose('nimsgears.templates.activate')
    def activate(self, **kwargs):
        return self.prefs()

    @expose('nimsgears.templates.prefs')
    def prefs(self, **kwargs):
        user = request.identity['user']

        if kwargs:
            DBSession.add(user)
            for key, value in kwargs.iteritems():
                setattr(user, key, value)
            flash(l_('Your settings have been updated.'))

        if not user.name or not user.email:
            ldap_name, ldap_email = nimsutil.ldap_query(user.id)
        name = user.name or ldap_name
        email = user.email or ldap_email

        prefs = OrderedDict(
                name = ('Display Name', name),
                email = ('Email Address', email)
                )

        return dict(page='prefs', prefs=prefs)

    @expose('nimsgears.templates.status')
    def status(self):
        #if not predicates.in_group('active_users').is_met(request.environ):
        #    flash(l_('Your account is not yet active.'))
        #    redirect('/auth/prefs')
        return dict(page='status', params={})

    @expose('nimsgears.templates.browse')
    def browse(self, **kwargs):
        user = request.identity['user'] if request.identity else None

        columns = ['Date & Time', 'Group', 'Experiment', 'MRI Exam #', 'Subject Name']
        datatypes = ['Dicom', 'NIfTI', 'SPM NIfTI', 'k-Space']
        searchByOptions = ['Subject Name', 'Group'];

        query = DBSession.query(Session, Experiment, Subject, ResearchGroup)
        query = query.join(Experiment, Session.experiment)
        query = query.join(Subject, Session.subject)
        query = query.join(ResearchGroup, Experiment.owner)

        query = query.join(Access, Experiment.accesses)
        #query = query.filter(Access.user==user)

        if 'Subject Name' in kwargs and kwargs['Subject Name']:
            query_str = kwargs['Subject Name'].replace('*', '%')
            query = query.filter(Subject.lastname.ilike(query_str))

        if 'Group' in kwargs and kwargs['Group']:
            query_str = kwargs['Group'].replace('*', '%')
            query = query.filter(ResearchGroup.id.ilike(query_str))

        results = query.all()

        sessiondata = [(r.Session.id, r.Session.timestamp.strftime('%Y-%m-%d %H:%M:%S'), r.Experiment.owner, r.Experiment, r.Session.mri_exam, r.Subject) for r in results]

        filter_info = {}
        experiments = sorted(set([r.Experiment for r in results]), key=lambda exp: exp.name)
        for exp in experiments:
            filter_info[exp.owner.id] = filter_info.get(exp.owner.id, []) + [exp.name]
        filter_info = sorted([(k,v) for k,v in filter_info.iteritems()], key=lambda tup: tup[0])

        return dict(page='browse', filter_info=filter_info, datatypes=datatypes, columns=columns, sessiondata=sessiondata, searchByOptions=searchByOptions)

    @expose('nimsgears.templates.search')
    def search(self):
        dataset_cnt = len(Session.query.all())
        return dict(page='search', dataset_cnt=dataset_cnt)

    @expose('nimsgears.templates.manage')
    def manage(self):
        return dict(page='manage', params={})

    @expose('nimsgears.templates.admin')
    def admin(self):
        return dict(page='admin', params={})

    @expose(content_type='application/x-tar')
    def download(self, *args, **kwargs):
        session_id = kwargs['session_id']
        query = DBSession.query(Dataset)
        query = query.join(Epoch, Dataset.epoch).join(Session, Epoch.session)
        results = query.filter(Session.id == session_id).all()

        paths = ' '.join([dataset.path for dataset in results])

        import shlex
        import subprocess as sp
        tar_proc = sp.Popen(shlex.split('tar -czf - %s' % paths), stdout=sp.PIPE, cwd=config.get('store_path'))
        return tar_proc.stdout
