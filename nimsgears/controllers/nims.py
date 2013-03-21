# @author:  Reno Bowen
#           Gunnar Schaefer

from tg import expose, request
import json

from nimsgears.model import *
from nimsgears.lib.base import BaseController


class NimsController(BaseController):

    @expose()
    def trash_flag(self, **kwargs):
        return json.dumps(request.identity['user'].trash_flag)

    def _modify_access(self, user, exp_list, user_list, set_to_privilege):
        success = True
        for exp in exp_list:
            for user_ in user_list:
                if (user_ not in exp.owner.pis) or user.is_superuser:
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

    def get_experiments(self, user):
        exp_data_list = []
        exp_attr_list = []
        for exp, acc_priv in user.experiments_with_access_privilege():
            exp_data_list.append((exp.owner.gid, exp.name))
            exp_attr_list.append({'id':'exp=%d' % exp.id, 'class':'access_%s %s' % (acc_priv.lower(), 'trash' if exp.trashtime else '')})
        return (exp_data_list, exp_attr_list)

    def get_sessions(self, user, exp_id):
        sess_data_list = []
        sess_attr_list = []
        for sess in user.sessions(exp_id):
            sess_data_list.append((sess.timestamp.strftime('%Y-%m-%d %H:%M'), sess.subject.code))
            sess_attr_list.append({'id':'sess=%d' % sess.id, 'class':'%s' % ('trash' if sess.trashtime else '')})
        return (sess_data_list, sess_attr_list)

    def get_epochs(self, user, sess_id):
        epoch_data_list = []
        epoch_attr_list = []
        for epoch in user.epochs(sess_id):
            epoch_data_list.append((epoch.timestamp.strftime('%H:%M:%S'), '%s' % epoch.description))
            epoch_attr_list.append({'id':'epoch=%d' % epoch.id, 'class':'%s' % ('trash' if epoch.trashtime else '')})
        return (epoch_data_list, epoch_attr_list)

    def get_datasets(self, user, epoch_id):
        dataset_data_list = []
        dataset_attr_list = []
        for dataset in user.datasets(epoch_id):
            dataset_data_list.append((dataset.label + ('*' if dataset.kind == u'primary' else ''),))
            dataset_attr_list.append({'id':'dataset=%d' % dataset.id, 'class':'%s' % ('trash' if dataset.trashtime else '')})
        return (dataset_data_list, dataset_attr_list)
