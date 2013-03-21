# @author:  Reno Bowen

from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
import transaction
import json

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController


class ExperimentsController(NimsController):

    @expose('nimsgears.templates.experiments')
    def index(self, **kw):
        user = request.identity['user']

        users = User.query.all()
        user_data_list = [(user.uid, user.name) for user in users]
        user_attr_list = [{'id': 'uid=%s' % user.uid} for user in users]

        exp_columns = [('Owner', 'col_sunet'), ('Name', 'col_name')]
        user_columns = [('SUNet ID', 'col_sunet'), ('Name', 'col_name')]

        return dict(page='experiments',
                    user_data_list=user_data_list,
                    user_attr_list=user_attr_list,
                    user_columns=user_columns,
                    exp_columns=exp_columns,
                    )

    @expose()
    def experiments_with_access(self, **kwargs):
        user = request.identity['user']
        requested_user = User.query.filter_by(uid=kwargs['id']).first()
        exp_with_acc_priv = requested_user.experiments_with_access_privilege()
        if user != requested_user:
            experiments = set(user.experiments(u'Manage')) & set(requested_user.experiments())
            exp_with_acc_priv = [(exp, acc_priv) for exp, acc_priv in exp_with_acc_priv if exp in experiments]
        return json.dumps(dict(success=True, access_levels=dict([('exp=%s' % exp.id, ap) for exp, ap in exp_with_acc_priv])))

    @expose()
    def users_with_access(self, **kwargs):
        user = request.identity['user']
        exp = Experiment.get(int(kwargs['id']))
        return json.dumps(dict(success=True, access_levels=dict([('uid=%s' % u.uid, ap) for u, ap in exp.users_with_access_privilege(user)])))

    @expose()
    def get_access_privileges(self, **kwargs):
        return json.dumps(AccessPrivilege.names())

    @expose()
    def modify_access(self, **kwargs):
        user = request.identity['user']
        exp_id_list = user_id_list = access_level = None
        if "exp_ids" in kwargs:
            exp_id_list = kwargs['exp_ids']
            if isinstance(exp_id_list, list):
                exp_id_list = [int(item) for item in exp_id_list]
            else:
                exp_id_list = [exp_id_list]
        if "user_ids" in kwargs:
            user_id_list = kwargs['user_ids']
            if not isinstance(user_id_list, list):
                user_id_list = [user_id_list]
        if "access_level" in kwargs:
            access_level = kwargs['access_level']

        result = {}
        result['success'] = False
        if exp_id_list and user_id_list and access_level:
            db_query = Experiment.query

            if not user.is_superuser:
                db_query = db_query.join(Access).filter(Access.user == user).filter(Access.privilege == AccessPrivilege.value(u'Manage'))

            db_result_exps = db_query.filter(Experiment.id.in_(exp_id_list)).all()

            if len(db_result_exps) == len(exp_id_list):
                db_result_users = User.query.filter(User.uid.in_(user_id_list)).all()
                result['success'] = self._modify_access(user, db_result_exps, db_result_users, AccessPrivilege.value(access_level))
        if result['success']:
            transaction.commit()
        else:
            transaction.abort()

        return json.dumps(result)
