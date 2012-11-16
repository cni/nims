# @author:  Reno Bowen

from tg import expose, request
from repoze.what import predicates
import transaction

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController

import json


class ExperimentsController(NimsController):

    @expose('nimsgears.templates.experiments')
    def index(self):
        user = request.identity['user']

        exp_data_list, exp_attr_list = self.get_experiments(user, True)
        for exp_attr in exp_attr_list:
            exp_attr['class'] = '' # don't need attributes in this case

        users = User.query.all()
        user_data_list = [(user.uid, user.name) for user in users]
        user_attr_list = [{'id': 'uid=%s' % user.uid} for user in users]

        exp_columns = [('Owner', 'col_sunet'), ('Name', 'col_name')]
        user_columns = [('SUNet ID', 'col_sunet'), ('Name', 'col_name')]
        acc_columns = [('SUNet ID', 'col_sunet'), ('Name', 'col_name'), ('Access Level', 'col_access')]

        return dict(page='experiments',
                    user_data_list=user_data_list,
                    user_attr_list=user_attr_list,
                    acc_columns=acc_columns,
                    exp_data_list=exp_data_list,
                    exp_attr_list=exp_attr_list,
                    user_columns=user_columns,
                    exp_columns=exp_columns,
                    )

    @expose()
    def experiments_with_access(self, **kwargs):
        """ Return ids of experiments the specified user has access to (and the
        level of that access), intersected with those ids that the requesting user
        has manage access to.
        """
        user = request.identity['user']
        id_ = kwargs['id']

        # User we are requesting an experiment list from
        requested_user = User.query.filter_by(uid=id_).first()

        # The requester needs to have manage access on an experiment to have
        # permission to see that another user has access to it
        visible_to_requester = user.get_experiments(including_trash=True, with_privilege=u'Manage')
        # We then retrieve all things that the requested user has *any* form of
        # access to
        visible_to_requested_user = requested_user.get_experiments(including_trash=True)

        # Then perform a set intersection to determine those common to the two sets
        key_list = set(visible_to_requester.keys()) & set(visible_to_requested_user.keys())
        acc_list = [AccessPrivilege.privilege_names[visible_to_requested_user[key].Access.privilege] for key in key_list]
        id_list = ['exp_%d' % key for key in key_list]
        access_levels = dict(zip(id_list, acc_list))

        return json.dumps(dict(success=True,
                               access_levels=access_levels))

    @expose()
    def users_with_access(self, **kwargs):
        """ Return ids of users that have access to the given experiment under the
        condition that the user requesting the information has manage access to the
        experiment.
        """
        user = request.identity['user']
        id_ = int(kwargs['id'])
        db_query = Experiment.query.filter_by(id=id_)
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        id_list = [access.user.uid for access in db_result.accesses]
        acc_list = [AccessPrivilege.privilege_names[access.privilege] for access in db_result.accesses]
        access_levels = dict(zip(id_list, acc_list))

        return json.dumps(dict(success=True,
                               access_levels=access_levels))

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
