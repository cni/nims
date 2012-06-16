# @author:  Reno Bowen

from tg import expose, request
from repoze.what import predicates
import transaction

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController

import json


class GroupsController(NimsController):

    @expose('nimsgears.templates.groups')
    def index(self):
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

def get_user_tuple(user_object):
    return (user_object.uid, user_object.name if user_object.name else 'None')

def get_groups_dict(group):
    group_dict = {}
    group_dict['members'], group_dict['admins'], group_dict['pis'], group_dict['others'] = {'data':[], 'attrs':[]}, {'data':[], 'attrs':[]}, {'data':[], 'attrs':[]}, {'data':[], 'attrs':[]}
    if group:
        others = User.query.all()
        for key, users in [('members', group.members), ('admins', group.managers), ('pis', group.pis)]:
            for user in users:
                group_dict[key]['data'].append(get_user_tuple(user))
                group_dict[key]['attrs'].append({'id':user.uid})
                others.remove(user)
        group_dict['others']['data'] = [get_user_tuple(user) for user in others]
        group_dict['others']['attrs'] = [{'id':user.uid} for user in others]
    return group_dict
