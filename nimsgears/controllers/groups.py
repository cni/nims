# @author:  Reno Bowen

from tg import expose, request
import transaction
import json

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController


class GroupsController(NimsController):

    @expose('nimsgears.templates.groups')
    def index(self):
        user = request.identity['user']
        return dict(
                page='groups',
                user_columns = [('SUNet ID', 'col_sunet'), ('Name', 'col_name')],
                research_groups = user.admin_groups,
                )

    @expose()
    def members_query(self, **kwargs):
        user = request.identity['user']
        group = ResearchGroup.get_by(gid=kwargs.get('research_group'))
        groups_dict = {
                'pis': {'attrs': [], 'data': []},
                'admins': {'attrs': [], 'data': []},
                'members': {'attrs': [], 'data': []},
                'others': {'attrs': [], 'data': []},
                }
        if user.manages_group(group):
            others = User.query.filter(~User.uid.in_(group.all_member_ids)).all()
            for key, users in [('pis', group.pis), ('admins', group.managers), ('members', group.members), ('others', others)]:
                for user in users:
                    groups_dict[key]['data'].append((user.uid, user.name))
                    groups_dict[key]['attrs'].append({'id':user.uid})
        return json.dumps(groups_dict)

    @expose()
    def modify_groups(self, **kwargs):
        user = request.identity['user']
        group_id = kwargs.get('group_id')
        membership_src = kwargs.get('membership_src')
        membership_dst = kwargs.get('membership_dst')
        user_id_list = None
        if 'user_ids' in kwargs:
            user_id_list = kwargs['user_ids'] if isinstance(kwargs['user_ids'], list) else [kwargs['user_ids']]
        change_retroactive = None
        if 'is_retroactive' in kwargs:
            change_retroactive = True if kwargs['is_retroactive'] == 'true' else False
        result = {'success': False}
        if all([group_id, membership_src, membership_dst, user_id_list]) and change_retroactive is not None:
            group = ResearchGroup.get_by(gid=group_id)
            if group:
                members = {'pis': (group.pis, u'Manage'), 'admins': (group.managers, u'Manage'), 'members': (group.members, u'Read-Only')}
                users = User.query.filter(User.uid.in_(user_id_list)).all()
                if user.manages_group(group) and ((membership_src != 'pis' and membership_dst != 'pis') or user.is_group_pi(group)):
                    result['success'] = True
                    if membership_src in members:
                        for u in users:
                            members[membership_src][0].remove(u)
                        if change_retroactive:
                            exp_list = Experiment.query.filter_by(owner=group).all()
                            result['success'] = self._modify_access(user, exp_list, users, None)
                    if membership_dst in members:
                        for u in users:
                            members[membership_dst][0].append(u)
                        if change_retroactive:
                            exp_list = Experiment.query.filter_by(owner=group).all()
                            result['success'] = self._modify_access(user, exp_list, users, members[membership_dst][1])
        if result['success']:
            transaction.commit()
        else:
            transaction.abort()
        return json.dumps(result)
