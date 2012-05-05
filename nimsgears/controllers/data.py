# -*- coding: utf-8 -*-
"""Sample controller with all its actions protected."""
from tg import config, expose, flash, redirect, request, response, require, session
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates
from tgext.admin.controller import AdminController
from tgext.admin.tgadminconfig import TGAdminConfig

import os
import shlex
import subprocess as sp
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
        import tempfile
        tempdir = tempfile.mkdtemp()
        store_path = config.get('store_path')

        session_id = kwargs['session_id']
        session = Session.query.filter(Session.id == session_id).first()
        datasets = Dataset.query.join(Epoch, Dataset.container).filter(Epoch.session == session).all()
        tardir = nimsutil.make_joined_path(tempdir, session.name)
        for dataset in datasets:
            os.symlink(os.path.join(store_path, dataset.relpath), os.path.join(tardir, dataset.name))
        tar_proc = sp.Popen(shlex.split('tar -cLf - %s' % session.name), stdout=sp.PIPE, cwd=tempdir)
        response.headerlist.append(('Content-Disposition', 'attachment; filename=%s' % session.name))
        return tar_proc.stdout

    @expose()
    def modify_groups(self, **kwargs):
        user = request.identity['user']

        user_id_list = group_id = membership_src = membership_dst = is_retroactive = None
        if "user_ids" in kwargs:
            user_id_list = kwargs["user_ids"]
            if not isinstance(user_id_list, list):
                user_id_list = [user_id_list]
        if "group_id" in kwargs:
            group_id = kwargs["group_id"]
        if "membership_src" in kwargs:
            membership_src = kwargs["membership_src"]
        if "membership_dst" in kwargs:
            membership_dst = kwargs["membership_dst"]
        if "is_retroactive" in kwargs:
            is_retroactive = True if kwargs["is_retroactive"] == 'true' else False

        result = {'success': False}
        if user_id_list and group_id and membership_src and membership_dst:
            db_result_group = ResearchGroup.query.filter_by(gid=group_id).first()
            if db_result_group:
                membership_dict = ({
                        'pis': (db_result_group.pis, 'mg'),
                        'admins': (db_result_group.managers, 'mg'),
                        'members': (db_result_group.members, 'ro'),
                        'others': ([], None)
                    })

                db_result_users = User.query.filter(User.uid.in_(user_id_list)).all()
                unsafe_transaction = ((user not in db_result_group.pis and user not in db_result_group.managers) or
                                     ((membership_src == 'pis' or membership_dst == 'pis') and user not in db_result_group.pis) or
                                     (membership_src == 'pis' and len(db_result_group.pis) == len(db_result_users)))
                if not unsafe_transaction or (predicates.in_group('superusers') and user.admin_mode):
                    result['success'] = True
                    if membership_src != 'others' and membership_src in membership_dict:
                        for item in db_result_users:
                            if item in membership_dict[membership_src][0]:
                                membership_dict[membership_src][0].remove(item)
                    if membership_dst in membership_dict:
                        if is_retroactive:
                            set_to_privilege = AccessPrivilege.query.filter_by(name=membership_dict[membership_dst][1]).first()
                            exp_list = Experiment.query.filter_by(owner=db_result_group).all()
                            result['success'] = self._modify_access(user, exp_list, db_result_users, set_to_privilege)
                        [membership_dict[membership_dst][0].append(item) for item in db_result_users]
        if result['success']:
            transaction.commit()
        else:
            transaction.abort()

        return json.dumps(result)

    @expose()
    def get_access_privileges(self, **kwargs):
        db_result_accpriv = AccessPrivilege.query.all()
        accpriv_list = [accpriv.description for accpriv in db_result_accpriv]
        return json.dumps(accpriv_list)

    def _modify_access(self, user, exp_list, user_list, set_to_privilege):
        success = True

        for exp in exp_list:
            for user_ in user_list:
                if (user_ not in exp.owner.pis) or (predicates.in_group('superusers') and user.admin_mode):
                    acc = Access.query.filter(Access.experiment == exp).filter(Access.user == user_).first()
                    if acc:
                        if set_to_privilege:
                            acc.privilege = set_to_privilege
                        else:
                            acc.delete()
                    else:
                        if set_to_privilege:
                            Access(experiment=exp, user=user_, privilege=set_to_privilege)
                else:
                    # user is a pi on that exp - you shouldn't be able to modify their access
                    success = False
                    break
            if not success:
                break

        return success

    def filter_access(self, db_query, user):
        db_query = db_query.join(Access).join(AccessPrivilege)
        if not (predicates.in_group('superusers') and user.admin_mode):
            mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
            db_query = db_query.filter(Access.user == user).filter(AccessPrivilege.value >= mg_privilege.value)
        return db_query

    def get_popup_data_experiment(self, user, id_):
        db_query = Experiment.query.filter_by(id=id_)
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'experiment',
            'name': db_result.name
            }

    def get_popup_data_session(self, user, id_):
        db_query = (Session.query.filter_by(id=id_)
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'session',
            'name': db_result.name
            }

    def get_popup_data_epoch(self, user, id_):
        db_query = (Epoch.query.filter_by(id=id_)
            .join(Session, Epoch.session)
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'epoch',
            'name': db_result.name
            }

    def get_popup_data_dataset(self, user, id_):
        db_query = (Dataset.query.filter_by(id=id_)
            .join(Epoch)
            .join(Session, Epoch.session)
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'dataset',
            'name': db_result.__class__.__name__
            }

    @expose()
    def get_popup_data(self, **kwargs):
        user = request.identity['user']
        popup_data = []
        if "exp_id" in kwargs:
            try:
                id_ = int(kwargs["exp_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_experiment(user, id_)

        elif "sess_id" in kwargs:
            try:
                id_ = int(kwargs["sess_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_session(user, id_)

        elif "epoch_id" in kwargs:
            try:
                id_ = int(kwargs["epoch_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_epoch(user, id_)

        elif "dataset_id" in kwargs:
            try:
                id_ = int(kwargs["dataset_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_dataset(user, id_)

        popup_data.update({'success': True})
        return json.dumps(popup_data)

    @expose()
    def modify_access(self, **kwargs):
        user = request.identity['user']
        exp_id_list = user_id_list = access_level = None
        if "exp_ids" in kwargs:
            exp_id_list = kwargs["exp_ids"]
            if isinstance(exp_id_list, list):
                exp_id_list = [int(item) for item in exp_id_list]
            else:
                exp_id_list = [exp_id_list]
        if "user_ids" in kwargs:
            user_id_list = kwargs["user_ids"]
            if not isinstance(user_id_list, list):
                user_id_list = [user_id_list]
        if "access_level" in kwargs:
            access_level = kwargs["access_level"]

        result = {}
        result['success'] = False
        if exp_id_list and user_id_list and access_level:
            db_query = Experiment.query

            if not (predicates.in_group('superusers') and user.admin_mode):
                mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
                db_query = db_query.join(Access).filter(Access.user == user)
                db_query = db_query.filter(Access.privilege == mg_privilege)

            db_result_exps = db_query.filter(Experiment.id.in_(exp_id_list)).all()

            if len(db_result_exps) == len(exp_id_list):
                set_to_privilege = AccessPrivilege.query.filter_by(description=access_level).first()
                db_result_users = User.query.filter(User.uid.in_(user_id_list)).all()
                result['success'] = self._modify_access(user, db_result_exps, db_result_users, set_to_privilege)
        if result['success']:
            transaction.commit()
        else:
            transaction.abort()

        return json.dumps(result)

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
        user = request.identity['user']
        id_list = query_type = db_query = None
        if "exp" in kwargs:
            id_list = kwargs["exp"]
            query_type = Experiment
            db_query = Experiment.query
        elif "sess" in kwargs:
            id_list = kwargs["sess"]
            query_type = Session
            db_query = (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        elif "epoch" in kwargs:
            id_list = kwargs["epoch"]
            query_type = Epoch
            db_query = (Epoch.query
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        elif "dataset" in kwargs:
            id_list = kwargs["dataset"]
            query_type = Dataset
            db_query = (Dataset.query
                .join(Epoch)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        db_query = db_query.join(Access).join(AccessPrivilege)

        result = {'success': False}
        if id_list and query_type and db_query:
            if isinstance(id_list, list):
                id_list = [int(item) for item in id_list]
            else:
                id_list = [id_list]

            db_query = db_query.filter(query_type.id.in_(id_list))

            if not (predicates.in_group('superusers') and user.admin_mode):
                mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
                db_query = db_query.filter(Access.user == user).filter(AccessPrivilege.value >= mg_privilege.value)

            db_result = db_query.all()

            # Verify that we still have all of the requested items after access
            # filtering
            if len(db_result) == len(id_list):
                result['success'] = True
                result['untrashed'] = False
                all_trash = True
                for db_item in db_result:
                    if all_trash and db_item.trashtime == None:
                        all_trash = False
                if not all_trash:
                    for db_item in db_result:
                        db_item.trash()
                else:
                    for db_item in db_result:
                        db_item.untrash()
                    result['untrashed'] = True
                transaction.commit()

        return json.dumps(result)

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
    def transfer_sessions(self, **kwargs):
        """ Queries DB given info found in POST, TODO perhaps verify access level another time here??
        """
        user = request.identity['user']

        sess_id_list = exp_id = None
        if "sess_id_list" in kwargs:
            sess_id_list = kwargs["sess_id_list"]
            if isinstance(sess_id_list, list):
                sess_id_list = [int(item) for item in kwargs["sess_id_list"]]
            else:
                sess_id_list = [sess_id_list]
        if "exp_id" in kwargs:
            exp_id = int(kwargs["exp_id"])

        result = {'success': False}

        if sess_id_list and exp_id:
            mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
            exp = DBSession.query(Experiment).filter_by(id = exp_id).one()
            db_query = DBSession.query(Session).join(Subject, Session.subject).join(Experiment, Subject.experiment).join(Access).join(AccessPrivilege).filter(Session.id.in_(sess_id_list))
            if not (predicates.in_group('superusers') and user.admin_mode):
                db_query = db_query.filter(Access.user == user).filter(AccessPrivilege.value >= mg_privilege.value)
            db_result_sess = db_query.all()

            # Verify that we still have all of the requested sessions after access filtering
            if len(db_result_sess) == len(sess_id_list):
                result['success'] = True
                result['untrashed'] = False
                all_trash = True
                for session in db_result_sess:
                    session.subject.experiment = exp
                    if all_trash and session.trashtime == None:
                        all_trash = False
                if not all_trash:
                    if session.subject.experiment.trashtime != None:
                        session.subject.experiment.untrash()
                        result['untrashed'] = True

                transaction.commit()

        return json.dumps(result)

    def get_experiments(self, user, trash_flag=None, manager_only=False):
        exp_data_list = []
        exp_attr_list = []

        if not trash_flag:
            trash_flag = self._get_trash_flag(user)

        db_query = DBSession.query(Experiment) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Experiment.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.join(Subject, Experiment.subjects).join(Session, Subject.sessions).join(Epoch, Session.epochs)
            db_query = db_query.filter((Experiment.trashtime != None) | (Session.trashtime != None) | (Epoch.trashtime != None))

        # If a superuser, ignore access items and set all to manage
        acc_str_list = []
        if predicates.in_group('superusers') and user.admin_mode:
            db_result_exp = db_query.all()
            acc_str_list = ['mg'] * len(db_result_exp)
        else: # Otherwise, populate access list with relevant entries
            db_query = db_query.add_entity(Access).join(Access).filter(Access.user == user)
            if manager_only:
                mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
                db_query = db_query.filter(Access.privilege == mg_privilege)
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

        db_query = DBSession.query(Session).join(Subject, Session.subject).join(Experiment, Subject.experiment).filter(Experiment.id == exp_id) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Session.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.join(Epoch, Session.epochs).filter((Session.trashtime != None) | (Epoch.trashtime != None))

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
            #subject_name = unicode(sess.subject_role.subject) if acc_priv_list[i] != 0 else 'Anonymous'
            sess_data_list.append((sess.subject.code, sess.timestamp.strftime('%Y-%m-%d %H:%M')))
            sess_attr_list.append({})
            sess_attr_list[i]['id'] = 'sess_%d' % sess.id
            if sess.trashtime != None:
                sess_attr_list[i]['class'] = 'trash'

        return (sess_data_list, sess_attr_list)

    def get_datasets(self, user, epoch_id):
        dataset_data_list = []
        dataset_attr_list = []

        trash_flag = self._get_trash_flag(user)

        db_query = (DBSession.query(Dataset)
                    .join(Epoch)
                    .filter(Epoch.id == epoch_id)
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    ) # get query set up

        if trash_flag == 0: # when trash flag off, only accept those with no trash time
            db_query = db_query.filter(Dataset.trashtime == None)
        elif trash_flag == 2: # when trash flag on, make sure everything is or contains trash
            db_query = db_query.filter(Dataset.trashtime != None)

        if predicates.in_group('superusers') and user.admin_mode:
            db_result_dataset = db_query.all()
        else:
            db_query = db_query.add_entity(Access).join(Access).filter(Access.user == user)
            db_result = db_query.all()
            db_result_dataset, db_result_acc = map(list, zip(*db_result)) if db_result else ([], [])

        for i in range(len(db_result_dataset)):
            dataset = db_result_dataset[i]
            dataset_data_list.append((dataset.__class__.__name__,))
            dataset_attr_list.append({})
            dataset_attr_list[i]['id'] = 'dataset_%d' % dataset.id
            if dataset.trashtime != None:
                dataset_attr_list[i]['class'] = 'trash'

        return (dataset_data_list, dataset_attr_list)

    def get_epochs(self, user, sess_id):
        epoch_data_list = []
        epoch_attr_list = []

        trash_flag = self._get_trash_flag(user)

        db_query = (DBSession.query(Epoch)
                    .join(Session, Epoch.session)
                    .filter(Session.id == sess_id)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    )
# get query set up
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
            epoch_data_list.append((epoch.timestamp.strftime('%H:%M'), '%s' % epoch.description))
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
        if 'dataset_list' in kwargs:
            try:
                epoch_id = int(kwargs['dataset_list'])
            except:
                result['success'] = False
            else:
                data_list, attr_list = self.get_datasets(user, epoch_id)
                result['success'] = True
        elif 'epoch_list' in kwargs:
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
        session_columns = [('Subj. Code', 'col_exam'), ('Date & Time', 'col_sname')]
        epoch_columns = [('Time', 'col_sa'), ('Description', 'col_desc')]
        dataset_columns = [('Data Type', 'col_type')]

        return dict(page='browse',
                    exp_columns=exp_columns,
                    session_columns=session_columns,
                    epoch_columns=epoch_columns,
                    dataset_columns=dataset_columns,
                    )

    @expose('nimsgears.templates.groups')
    def groups(self):
        user = request.identity['user']

        if predicates.in_group('superusers') and user.admin_mode:
            research_groups = ResearchGroup.query.all()
        else:
            research_groups = user.pi_groups + user.manager_groups

        # all assigned to same list, but we reassign after anyway
        group = research_groups[0] if research_groups else None

        user_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name')]
        return dict(page='groups',
                    user_columns = user_columns,
                    research_groups = research_groups,
                    )

    @expose()
    def users_with_access(self, **kwargs):
        user = request.identity['user']
        id_ = int(kwargs['exp_id'])
        db_query = Experiment.query.filter_by(id=id_)
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        acc_data_list = []
        acc_attr_list = []
        if db_result:
            for access in db_result.accesses:
                acc_data_list.append((access.user.uid, access.user.name, access.privilege.__unicode__()))
                acc_attr_list.append({'class': access.privilege.name})
        return json.dumps(dict(success=True,
                               data=acc_data_list,
                               attrs=acc_attr_list))


    @expose()
    def groups_query(self, **kwargs):
        user = request.identity['user']
        group = None
        if 'research_group' in kwargs:
            group = kwargs['research_group']
            group = ResearchGroup.query.filter(ResearchGroup.gid == group).first()
            # Set group to None if the POSTed group is not actually on that users list of groups
            group = group if (group in user.pi_groups + user.manager_groups or predicates.in_group('superusers') and user.admin_mode) else None
        groups_dict = get_groups_dict(group)
        return json.dumps(groups_dict)

    @expose('nimsgears.templates.access')
    def access(self):
        user = request.identity['user']

        exp_data_list, exp_attr_list = self.get_experiments(user, 1, True)
        user_list = [(usr.uid, usr.name if usr.name else 'None') for usr in User.query.all()]

        # FIXME i plan to replace these things with just column number
        # indicators computed in the front end code... keep class names out of back end
        exp_columns = [('Owner', 'col_sunet'), ('Name', 'col_name')]
        user_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name')]
        acc_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name'), ('Access Level', 'col_access')]

        return dict(page='access',
                    user_list=user_list,
                    acc_columns=acc_columns,
                    exp_data_list=exp_data_list,
                    exp_attr_list=exp_attr_list,
                    user_columns=user_columns,
                    exp_columns=exp_columns,
                    )

def get_user_tuple(user_object):
    return (user_object.uid, user_object.name if user_object.name else 'None')

def get_groups_dict(group):
    group_dict = {}
    group_dict['members'], group_dict['admins'], group_dict['pis'], group_dict['others'] = {'data':[]}, {'data':[]}, {'data':[]}, {'data':[]}
    if group:
        others = User.query.all()
        for key, users in [('members', group.members), ('admins', group.managers), ('pis', group.pis)]:
            for user in users:
                group_dict[key]['data'].append(get_user_tuple(user))
                others.remove(user)
        group_dict['others']['data'] = [get_user_tuple(user) for user in others]
    return group_dict
