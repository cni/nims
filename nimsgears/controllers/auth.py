# @author:  Gunnar Schaefer

from tg import config, expose, flash, redirect, request, response
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates

import os
import time
import shlex
import subprocess
from collections import OrderedDict

import nimsutil
from nimsgears import model
from nimsgears.model import *

from nimsgears.lib.base import BaseController
from nimsgears.controllers.access import AccessController
from nimsgears.controllers.browse import BrowseController
from nimsgears.controllers.search import SearchController
from nimsgears.controllers.groups import GroupsController

import json

__all__ = ['AuthController']


class AuthController(BaseController):

    access = AccessController()
    browse = BrowseController()
    search = SearchController()
    groups = GroupsController()

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

    @expose('nimsgears.templates.toggle_admin')
    def toggle_admin(self, came_from):
        user = request.identity['user']
        DBSession.add(user)
        user.admin_mode = not user.admin_mode
        redirect(came_from)

    @expose('nimsgears.templates.prefs')
    def prefs(self, **kwargs):
        user = request.identity['user']

        if kwargs:
            DBSession.add(user)
            for key, value in kwargs.iteritems():
                setattr(user, key, value)
            flash(l_('Your settings have been updated.'))

        if not user.firstname or not user.lastname or not user.email:
            ldap_firstname, ldap_lastname, ldap_email = nimsutil.ldap_query(user.uid)
        firstname = user.firstname or ldap_firstname
        lastname = user.lastname or ldap_lastname
        email = user.email or ldap_email

        prefs = OrderedDict()
        prefs['firstname'] = ('First Name', firstname)
        prefs['lastname'] = ('Last Name', lastname)
        prefs['email'] = ('Email Address', email)

        return dict(page='prefs', prefs=prefs)

    @expose('nimsgears.templates.status')
    def status(self):
        #if not predicates.in_group('active_users').is_met(request.environ):
        #    flash(l_('Your account is not yet active.'))
        #    redirect('/auth/prefs')

        failed_jobs = Job.query.filter(Job.status == u'failed').all()
        active_jobs = Job.query.filter(Job.status == u'active').all()
        new_jobs = Job.query.filter(Job.status == u'new').all()
        return dict(
                page='status',
                failed_jobs=failed_jobs,
                active_jobs=active_jobs,
                new_jobs=new_jobs,
                )

    @expose('nimsgears.templates.admin')
    def admin(self):
        return dict(page='admin', params={})

    @expose(content_type='image/png')
    def image(self, *args):
        return open('/tmp/image.png', 'r')

    @expose(content_type='application/octet-stream')
    def speed(self, *args):
        #return open('/boot/kernel/kernel.symbols', 'r')
        return subprocess.Popen(shlex.split('tar -cLf - %s' % '/boot/kernel/kernel.symbols'), stdout=subprocess.PIPE, cwd='/tmp').stdout

    @expose(content_type='application/x-tar')
    def download(self, **kwargs):
        user = request.identity['user']
        user_path = '%s/%s' % (config.get('links_path'), 'superuser' if user.is_superuser else user.uid)
        tar_dirs = None
        if 'id_dict' in kwargs and 'sess' in kwargs['id_dict']:
            query_type = Session
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['sess']]
            db_res = (DBSession.query(Session, Experiment, ResearchGroup, Dataset, Epoch)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(ResearchGroup, Experiment.owner)
                    .join(Epoch, Session.epochs)
                    .join(Dataset, Epoch.datasets)
                    .filter((Dataset.kind == u'secondary') | (Dataset.kind == u'derived'))
                    .filter(Session.id.in_(id_list))
                    .all())
            tar_dirs = ['%s/%s/%s/%s/%s' % (r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name, r.Dataset.name) for r in db_res]
        elif 'id_dict' in kwargs and 'dataset' in kwargs['id_dict']:
            query_type = Dataset
            id_list = [int(id) for id in json.loads(kwargs['id_dict'])['dataset']]
            db_res = (DBSession.query(Dataset, Epoch, Session, Experiment, ResearchGroup)
                    .join(Epoch, Dataset.container)
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(ResearchGroup, Experiment.owner)
                    .filter(Dataset.id.in_(id_list))
                    .all())
            tar_dirs = ['%s/%s/%s/%s/%s' % (r.ResearchGroup.gid, r.Experiment.name, r.Session.name, r.Epoch.name, r.Dataset.name) for r in db_res]
        if tar_dirs:
            #redirect('/%s/download.php?%s' % (user_path, '&'.join('dirs[%d]=%s' %(i, p) for i, p in enumerate(tar_dirs))))
            tar_proc = subprocess.Popen(shlex.split('tar -cLf - -C %s %s' % (user_path, ' '.join(tar_dirs))), stdout=subprocess.PIPE)
            response.headerlist.append(('Content-Disposition', 'attachment; filename=%s_%d' % ('nims', time.time())))
            return tar_proc.stdout
