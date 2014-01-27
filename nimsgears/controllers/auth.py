# @author:  Gunnar Schaefer

from tg import config, expose, flash, redirect, request, response
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates

import os
from collections import OrderedDict

import nimsutil
from nimsgears.model import *

from nimsgears.lib.base import BaseController
from nimsgears.controllers.browse import BrowseController
from nimsgears.controllers.search import SearchController
from nimsgears.controllers.experiments import ExperimentsController
from nimsgears.controllers.groups import GroupsController

__all__ = ['AuthController']

store_path = config.get('store_path')


class AuthController(BaseController):

    browse = BrowseController()
    search = SearchController()
    experiments = ExperimentsController()
    groups = GroupsController()

    allow_only = predicates.not_anonymous(msg=l_('You must be logged in to view this page.'))

    # FIXME: handle deactivated users
    #active_user = predicates.in_group('users', msg=l_('Your account is inactive. You can request activation below.'))

    def _not_active_user(msg):
        flash(msg)
        redirect('/auth/activate')

    @expose()
    def index(self):
        redirect('/auth/browse')

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
            ldap_firstname, ldap_lastname, ldap_email, ldap_uid_number = nimsutil.ldap_query(user.uid)
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

        failed_jobs = Job.query.filter(Job.status == u'failed').order_by(Job.id).all()
        active_jobs = Job.query.filter(Job.status == u'running').order_by(Job.id).all()
        queued_jobs = Job.query.filter(Job.status == u'pending').order_by(Job.id).limit(200).all()
        return dict(
                page='status',
                failed_jobs=failed_jobs,
                active_jobs=active_jobs,
                queued_jobs=queued_jobs,
                )

    @expose('nimsgears.templates.admin')
    def admin(self):
        return dict(page='admin', params={})
