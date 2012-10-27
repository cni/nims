# @author:  Reno Bowen

from tg import expose, request
from repoze.what import predicates
import transaction

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController

import json


class AccessController(NimsController):

    @expose('nimsgears.templates.access')
    def index(self):
        user = request.identity['user']

        exp_data_list, exp_attr_list = self.get_experiments(user, True)
        users = User.query.all()
        user_data_list = [(user.uid, user.name) for user in users]
        user_attr_list = [{'id': 'uid=%s' % user.uid} for user in users]

        exp_columns = [('Owner', 'col_sunet'), ('Name', 'col_name')]
        user_columns = [('SUNet ID', 'col_sunet'), ('Name', 'col_name')]
        acc_columns = [('SUNet ID', 'col_sunet'), ('Name', 'col_name'), ('Access Level', 'col_access')]

        return dict(page='access',
                    user_data_list=user_data_list,
                    user_attr_list=user_attr_list,
                    acc_columns=acc_columns,
                    exp_data_list=exp_data_list,
                    exp_attr_list=exp_attr_list,
                    user_columns=user_columns,
                    exp_columns=exp_columns,
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
                acc_data_list.append((access.user.uid, access.user.name, AccessPrivilege.name(access.privilege)))
                acc_attr_list.append({'class': AccessPrivilege.name(access.privilege), 'id': 'uid=%s' % access.user.uid})
        return json.dumps(dict(success=True,
                               data=acc_data_list,
                               attrs=acc_attr_list))

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
