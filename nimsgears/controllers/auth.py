# @author:  Gunnar Schaefer

from tg import config, expose, flash, redirect, request, response
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates

import os
import shlex
import subprocess as sp
from collections import OrderedDict

from nimsgears import model
from nimsgears.model import *

from nimsgears.lib.base import BaseController
from nimsgears.controllers.access import AccessController
from nimsgears.controllers.browse import BrowseController
from nimsgears.controllers.groups import GroupsController

import nimsutil

import json # return raw json to browser in cases of database queries
import transaction

__all__ = ['AuthController']


class AuthController(BaseController):

    access = AccessController()
    browse = BrowseController()
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

        if not user.name or not user.email:
            ldap_name, ldap_email = nimsutil.ldap_query(user.uid)
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

    @expose('nimsgears.templates.search')
    def search(self):
        dataset_cnt = len(Session.query.all())
        return dict(page='search', dataset_cnt=dataset_cnt)

    @expose('nimsgears.templates.admin')
    def admin(self):
        return dict(page='admin', params={})

    @expose(content_type='image/png')
    def image(self, *args):
        return open('/tmp/image.png', 'r')

    #@expose(content_type='application/x-tar')
    #def download(self, *args, **kwargs):
    #    import tempfile
    #    tempdir = tempfile.mkdtemp()
    #    store_path = config.get('store_path')

    #    session_id = kwargs['session_id']
    #    session = Session.query.filter(Session.id == session_id).first()
    #    datasets = Dataset.query.join(Epoch, Dataset.container).filter(Epoch.session == session).all()
    #    tardir = nimsutil.make_joined_path(tempdir, session.name)
    #    for dataset in datasets:
    #        os.symlink(os.path.join(store_path, dataset.relpath), os.path.join(tardir, dataset.name))
    #    tar_proc = sp.Popen(shlex.split('tar -cLf - %s' % session.name), stdout=sp.PIPE, cwd=tempdir)
    #    response.headerlist.append(('Content-Disposition', 'attachment; filename=%s' % session.name))
    #    return tar_proc.stdout

    @expose(content_type='application/octet-stream')
    def speed(self, *args):
        #tar_proc = sp.Popen(shlex.split('tar -cLf - %s' % '/usr/local/www/apache22/data/testing/P86016_.7'), stdout=sp.PIPE, cwd='/tmp')
        tar_proc = sp.Popen(shlex.split('cat %s' % '/usr/local/www/apache22/data/testing/P86016_.7'), stdout=sp.PIPE, cwd='/tmp')
        return tar_proc.stdout
        #return open('/usr/local/www/apache22/data/testing/P86016_.7', 'r')

    @expose()
    def download(self, **kwargs):
        user = request.identity['user']
        id_dict = None
        result = {}
        query_type = None
        if 'id_dict' in kwargs:
            id_dict = json.loads(kwargs['id_dict'])
            if 'sess' in id_dict:
                query_type = Session
                try:
                    id_list = id_dict['sess']
                    result['success'] = True
                except:
                    result['success'] = False
                else:
                    pass
            elif 'dataset' in id_dict:
                query_type = Dataset
                try:
                    id_list = id_dict['dataset']
                    result['success'] = True
                except:
                    result['success'] = False
                else:
                    pass
        if not isinstance(id_list, list):
            id_list = [id_list]
        print query_type
        print id_list
        return result
