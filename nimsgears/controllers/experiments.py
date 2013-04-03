# @author:  Reno Bowen

from tg import expose, request, tmpl_context, validate, flash, redirect, lurl, render
import transaction
import json

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController


class ExperimentsController(NimsController):

    @expose('nimsgears.templates.experiments')
    def index(self, **kw):
        return dict(
                page='experiments',
                user_columns=[('SUNet ID', 'col_sunet'), ('Name', 'col_name')],
                exp_columns=[('Owner', 'col_sunet'), ('Name', 'col_name')],
                )

    @expose()
    def experiments_with_access(self, **kwargs):
        user = request.identity['user']
        requested_user = User.query.filter_by(uid=kwargs['id']).first()
        exp_with_acc_priv = requested_user.experiments_with_access_privilege(ignore_superuser=True)
        if requested_user != user:
            experiments = set(user.experiments(u'Manage')) & set(requested_user.experiments(ignore_superuser=True))
            exp_with_acc_priv = [(exp, acc_priv) for exp, acc_priv in exp_with_acc_priv if exp in experiments]
        return json.dumps(dict(success=True, access_levels=dict([('exp=%s' % exp.id, acc_priv) for exp, acc_priv in exp_with_acc_priv])))

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
        exp_id_list = None
        user_id_list = None
        access_level = None
        if 'exp_ids' in kwargs:
            exp_id_list = kwargs['exp_ids'] if isinstance(kwargs['exp_ids'], list) else [kwargs['exp_ids']]
        if 'user_ids' in kwargs:
            user_id_list = kwargs['user_ids'] if isinstance(kwargs['user_ids'], list) else [kwargs['user_ids']]
        if 'access_level' in kwargs:
            access_level = kwargs['access_level']
        result = {'success': False}
        if exp_id_list and user_id_list and access_level:
            acc_exps = Experiment.query.filter(Experiment.id.in_(exp_id_list)).all()
            acc_users = User.query.filter(User.uid.in_(user_id_list)).all()
            result['success'] = self._modify_access(user, acc_exps, acc_users, access_level)
        if result['success']:
            transaction.commit()
        else:
            transaction.abort()
        return json.dumps(result)
