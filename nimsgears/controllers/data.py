# -*- coding: utf-8 -*-
"""Sample controller with all its actions protected."""
from tg import config, expose, flash, redirect, request, require, session
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
    def get_trash_flag(self, **kwargs):
        user = request.identity['user']
        trash_flag = self._get_trash_flag(user)
        return json.dumps(trash_flag)

    def _get_trash_flag(self, user):
        trash_flag = session.get(user.uid, 0)
        return trash_flag

    @expose()
    def set_trash_flag(self, **kwargs):
        user = request.identity['user']
        result = {}
        if 'trash_flag' in kwargs:
            try:
                trash_flag = int(kwargs['trash_flag'])
            except:
                result['success'] = False
            else:
                session[user.uid] = trash_flag
                session.save()
                result['success'] = True
        else:
            result['success'] = False
        return json.dumps(result)

    @expose()
    def trash(self, **kwargs):
        db_query = None
        query_type = None
        if "exp" in kwargs:
            id_list = kwargs["exp"]
            query_type = Experiment
        elif "sess" in kwargs:
            id_list = kwargs["sess"]
            query_type = Session
        elif "epoch" in kwargs:
            id_list = kwargs["epoch"]
            query_type = Epoch

        if isinstance(id_list, list):
            id_list = [int(item) for item in id_list]
        else:
            id_list = [id_list]

        db_result = query_type.query.filter(query_type.id.in_(id_list)).all()

        for db_item in db_result:
            db_item.trash()

        return json.dumps({'success':True})

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
        exp_id = int(kwargs["exp_id"])

        exp = DBSession.query(Experiment).filter_by(id = exp_id).one()
        sess_list = DBSession.query(Session).filter(Session.id.in_(sess_id_list)).all()
        for session in sess_list:
            session.experiment = exp

        transaction.commit()

        return json.dumps({"success":True})

    def get_experiments(self, user):
        exp_data_list = []
        exp_attr_list = []

        trash_flag = self._get_trash_flag(user)

        db_query = DBSession.query(Experiment) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Experiment.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.join(Session, Epoch).filter(or_(Experiment.trashtime != None, Session.trashtime != None, Epoch.trashtime != None))

        # If a superuser, ignore access items and set all to manage
        acc_str_list = []
        if predicates.in_group('superusers') and user.admin_mode:
            db_result_exp = db_query.all()
            acc_str_list = ['mg'] * len(db_result_exp)
        else: # Otherwise, populate access list with relevant entries
            db_query = db_query.add_entity(Access).join(Access).filter(Access.user == user)
            db_result = db_query.all()
            db_result_exp, db_result_acc = map(list, zip(*db_result)) if db_result else ([], [])
            acc_str_list = [acc.privilege.name for acc in db_result_acc]

        for i in range(len(db_result_exp)):
            exp = db_result_exp[i]
            exp_data_list.append((exp.owner.gid, exp.name))
            exp_attr_list.append({})
            exp_attr_list[i]['id'] = 'exp_%d' % exp.id
            exp_attr_list[i]['class'] = 'access_%s' % acc_str_list[i]
            if exp.trashtime != None:
                exp_attr_list[i]['class'] += ' trash'

        return (exp_data_list, exp_attr_list)

    def get_sessions(self, user, exp_id):
        sess_data_list = []
        sess_attr_list = []

        trash_flag = self._get_trash_flag(user)

        db_query = DBSession.query(Session).join(Experiment).filter(Experiment.id == exp_id) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Session.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.join(Epoch).filter(or_(Session.trashtime != None, Epoch.trashtime != None))

        acc_priv_list = []
        if predicates.in_group('superusers') and user.admin_mode:
            db_result_sess = db_query.all()
            acc_priv_list = [99] * len(db_result_sess) # arbitrary nonzero number to indicate > anonymized access
        else:
            db_query = db_query.add_entity(Access).join(Access).filter(Access.user == user)
            db_result = db_query.all()
            db_result_sess, db_result_acc = map(list, zip(*db_result)) if db_result else ([], [])
            acc_priv_list = [acc.privilege.value for acc in db_result_acc]

        n_results = len(db_result_sess)
        for i in range(n_results):
            sess = db_result_sess[i]
            subject_name = unicode(sess.subject) if acc_priv_list[i] != 0 else 'Anonymous'
            sess_data_list.append((sess.mri_exam, subject_name))
            sess_attr_list.append({})
            sess_attr_list[i]['id'] = 'sess_%d' % sess.id
            if sess.trashtime != None:
                sess_attr_list[i]['class'] = 'trash'

        return (sess_data_list, sess_attr_list)

    def get_epochs(self, user, exp_id):
        epoch_data_list = []
        epoch_attr_list = []

        trash_flag = self._get_trash_flag(user)

        db_query = DBSession.query(Epoch).join(Session, Experiment).filter(Session.id == exp_id) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Epoch.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.filter(Epoch.trashtime != None)

        if predicates.in_group('superusers') and user.admin_mode:
            db_result_epoch = db_query.all()
        else:
            db_query = db_query.add_entity(Access).join(Access).filter(Access.user == user)
            db_result = db_query.all()
            db_result_epoch, db_result_acc = map(list, zip(*db_result)) if db_result else ([], [])

        for i in range(len(db_result_epoch)):
            epoch = db_result_epoch[i]
            epoch_data_list.append(("%2d/%2d" % (epoch.mri_series, epoch.mri_acq), epoch.mri_desc))
            epoch_attr_list.append({})
            epoch_attr_list[i]['id'] = 'epoch_%d' % epoch.id
            if epoch.trashtime != None:
                epoch_attr_list[i]['class'] = 'trash'

        return (epoch_data_list, epoch_attr_list)

    @expose()
    def list_query(self, **kwargs):
        """ Return info about sessions for given experiment id."""
        user = request.identity['user']

        result = {}
        data_list, attr_list = [], []
        if 'epoch_list' in kwargs:
            try:
                sess_id = int(kwargs['epoch_list'])
            except:
                result['success'] = False
            else:
                data_list, attr_list = self.get_epochs(user, sess_id)
                result['success'] = True
        elif 'sess_list' in kwargs:
            try:
                exp_id = int(kwargs['sess_list'])
            except:
                result['success'] = False
            else:
                data_list, attr_list = self.get_sessions(user, exp_id)
                result['success'] = True
        elif 'exp_list' in kwargs:
            data_list, attr_list = self.get_experiments(user)
            result['success'] = True
        else:
            result['success'] = False

        result['data'], result['attrs'] = data_list, attr_list

        return json.dumps(result)

    @expose('nimsgears.templates.browse')
    def browse(self):
        user = request.identity['user']

        # Table columns and their relevant classes
        exp_columns = [('Group', 'col_sunet'), ('Experiment', 'col_name')]
        session_columns = [('Session', 'col_exam'), ('Subject Name', 'col_sname')]
        epoch_columns = [('Epoch', 'col_sa'), ('Description', 'col_desc')]

        return dict(page='browse',
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

