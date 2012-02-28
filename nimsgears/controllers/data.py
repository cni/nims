# -*- coding: utf-8 -*-
"""Sample controller with all its actions protected."""
from tg import config, expose, flash, redirect, request, require
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates
from tgext.admin.controller import AdminController
from tgext.admin.tgadminconfig import TGAdminConfig

from sqlalchemy import or_

from collections import OrderedDict

from nimsgears import model
from nimsgears.model import *

from nimsgears.lib.base import BaseController

import nimsutil

import json # return raw json to browser in cases of database queries
import transaction

__all__ = ['DataController', 'PublicDataController']


class NimsAdminConfig(TGAdminConfig):
    default_index_template = 'genshi:nimsgears.templates.tg_admin'


class NimsAdminController(AdminController):
    allow_only = predicates.in_group('superusers')


class DataController(BaseController):

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
        ## tried this to get async pipe working with paster, but doesn't seem to do anything
        ## should work outright with apache once python bug is fixed: http://bugs.python.org/issue13156
        #import fcntl, os
        #fd = tar_proc.stdout.fileno()
        #file_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        #fcntl.fcntl(fd, fcntl.F_SETFL, file_flags | os.O_NDELAY)
        return tar_proc.stdout

    @expose()
    def session_query(self, **kwargs):
        """ Return info about sessions for given experiment id."""
        user = request.identity['user']

        def session_tuple(session, axs_priv_val):
            return (session.id, session.mri_exam, unicode(session.subject) if axs_priv_val != 0 else 'Anonymous')

        try:
            exp_id = int(kwargs['id'])
        except:
            exp_id = -1

        if predicates.in_group('superusers') and user.admin_mode:
            results = Session.query.join(Experiment).filter(Experiment.id==exp_id).all()
            sessions = [session_tuple(session, -1) for session in results]
        else:
            query = DBSession.query(Session, Access).join(Experiment).join(Access)
            results = query.filter(Experiment.id==exp_id).filter(Access.user==user).all()
            sessions = [session_tuple(result.Session, result.Access.privilege.value) for result in results]
        return json.dumps(sessions)

    @expose()
    def update_epoch(self, **kwargs):
        user = request.identity['user']

        try:
            epoch_id = int(kwargs['id'])
            desc = kwargs['desc']
        except:
            epoch_id = -1
            desc = None

        rw_privilege = AccessPrivilege.query.filter_by(name = u'rw').first()
        epoch = DBSession.query(Epoch).join('session', 'experiment', 'access', 'privilege').filter(Epoch.id == epoch_id).filter(Access.user == user).filter(AccessPrivilege.value > rw_privilege.value).first()

        if epoch:
            epoch.mri_desc = desc
            transaction.commit()
            success = True
        else:
            success = False

        return json.dumps({'success':success})

    @expose()
    def epoch_query(self, **kwargs):
        """ Queries DB given info found in POST, TODO perhaps verify access level another time here??
        """
        def summarize_epoch(epoch, sess_id):
            return (epoch.id, "%2d/%2d" % (epoch.mri_series, epoch.mri_acq), epoch.mri_desc)

        try:
            sess_id = int(kwargs['id'])
        except:
            sess_id = -1

        epoch_list = ([summarize_epoch(item.Epoch, sess_id) for item in
            DBSession.query(Epoch, Session).join('session').filter(Session.id == sess_id).all()])

        return json.dumps(epoch_list)

    @expose()
    def transfer_sessions(self, **kwargs):
        """ Queries DB given info found in POST, TODO perhaps verify access level another time here??
        """
        # STILL NEED TO IMPLEMENT ACCESS CHECKING TODO
        # FOR NOW, JUST TRANSFERRING WITHOUT A CHECK SO I CAN DEMONSTRATE CONCEPT FIXME

        sess_id_list = kwargs["sess_id_list"]
        if isinstance(sess_id_list, list):
            sess_id_list = [int(item) for item in kwargs["sess_id_list"]]
        else:
            sess_id_list = [sess_id_list]
        print sess_id_list
        exp_id = int(kwargs["exp_id"])

        exp = DBSession.query(Experiment).filter_by(id = exp_id).one()
        sess_list = DBSession.query(Session).filter(Session.id.in_(sess_id_list)).all()
        for session in sess_list:
            session.experiment = exp

        transaction.commit()

        return json.dumps({"success":True})

    @expose('nimsgears.templates.browse')
    def browse(self):
        user = request.identity['user']

        exp_data_list = []
        exp_attr_list = []

        trash_flag = 2 # trash flag is off on first page load

        db_query = DBSession.query(Experiment, Access).join(Access) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Experiment.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.join(Session, Epoch).filter(or_(Experiment.trashtime != None, Session.trashtime != None, Epoch.trashtime != None))

        # If a superuser, ignore access items and set all to manage
        if predicates.in_group('superusers') and user.admin_mode:
            db_result = db_query.all()
            db_result_exp, db_result_acc = map(list, zip(*db_result)) if db_result else ([], [])
            exp_attr_list = [{'class':'access_mg'}] * len(db_result)
        else: # Otherwise, populate access list with relevant entries
            db_query = db_query.filter(Access.user == user)
            db_result = db_query.all()
            db_result_exp, db_result_acc = map(list, zip(*db_result)) if db_result else ([], [])
            exp_attr_list = [{'class':'access_%s' % acc.privilege.name} for acc in db_result_acc]

        for i in range(len(db_result_exp)):
            exp = db_result_exp[i]
            exp_data_list.append((exp.owner.gid, exp.name))
            exp_attr_list[i]['id'] = 'exp_%d' % exp.id
            if exp.trashtime != None:
                exp_attr_list[i]['class'] += ' trash'

        # Table columns and their relevant classes
        exp_columns = [('Group', 'col_sunet'), ('Experiment', 'col_name')]
        session_columns = [('Session', 'col_exam'), ('Subject Name', 'col_sname')]
        epoch_columns = [('Epoch', 'col_sa'), ('Description', 'col_desc')]

        return dict(page='browse',
                    exp_data_list = exp_data_list,
                    exp_attr_list = exp_attr_list,
                    exp_columns=exp_columns,
                    session_columns=session_columns,
                    epoch_columns=epoch_columns)

    @expose('nimsgears.templates.groups')
    def groups(self):
        user = request.identity['user']

        research_groups = user.pi_groups + user.admin_groups

        # all assigned to same list, but we reassign after anyway
        group = research_groups[0] if research_groups else None
        groups_dict = get_groups_dict(group)

        user_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name')]
        return dict(page='groups',
                    user_columns = user_columns,
                    research_groups = research_groups,
                    groups_dict = groups_dict,
                    )

    @expose()
    def groups_query(self, **kwargs):
        user = request.identity['user']
        group = None
        if 'research_group' in kwargs:
            group = kwargs['research_group']
            group = ResearchGroup.query.filter(ResearchGroup.gid == group).first()
            # Set group to None if the POSTed group is not actually on that users list of groups
            group = group if (group in user.pi_groups + user.admin_groups) else None
        groups_dict = get_groups_dict(group)
        return json.dumps(groups_dict)

    @expose('nimsgears.templates.access')
    def access(self):
        user = request.identity['user']

        exp_dict_dict = {} # exp_dict by access level
        access_levels = [u'mg']
        for access_level in access_levels:
            exp_dict = {} # exp by exp_id
            privilege = AccessPrivilege.query.filter_by(name=access_level).one()
            db_item_list = DBSession.query(Experiment, Access).join(Access).filter(Access.user == user).filter(Access.privilege == privilege).all()
            for db_item in db_item_list:
                exp = db_item.Experiment
                exp_dict[exp.id] = (exp.owner.gid, exp.name)
            exp_dict_dict[access_level] = exp_dict

        user_list = [(usr.uid, usr.name if usr.name else 'None') for usr in User.query.all()]

        # FIXME i plan to replace these things with just column number
        # indicators computed in the front end code... keep class names out of back end
        exp_columns = [('Owner', 'col_sunet'), ('Name', 'col_name')]
        user_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name')]

        access_levels.insert(0, u'pi')
        return dict(page='access',
                    user_list=user_list,
                    user_columns=user_columns,
                    exp_dict_dict=exp_dict_dict,
                    access_levels=access_levels,
                    exp_columns=exp_columns,
                    )

def get_user_tuple(user_object):
    return (user_object.uid, user_object.name if user_object.name else 'None')

def get_groups_dict(group):
    group_dict = {}
    group_dict['members'], group_dict['admins'], group_dict['pis'], group_dict['others'] = [], [], [], []
    if group:
        group_dict['others'] = User.query.all()
        for key, users in [('members', group.members), ('admins', group.admins), ('pis', group.pis)]:
            for user in users:
                group_dict[key].append(get_user_tuple(user))
                group_dict['others'].remove(user)
        group_dict['others'] = [get_user_tuple(user) for user in group_dict['others']]
    return group_dict

