# @author:  Reno Bowen
#           Gunnar Schaefer

from tg import expose, request
import json

from nimsgears.model import *
from nimsgears.lib.base import BaseController


class NimsController(BaseController):

    def _modify_access(self, user, exp_list, user_list, access_level):
        privilege = AccessPrivilege.value(access_level)
        success = True
        for exp in exp_list:
            if not user.has_access_to(exp, u'Manage'):
                success = False
                break
            for user_ in user_list:
                if user_ in exp.owner.pis: # no one can modify the access of a PI
                    success = False
                    break
                else:
                    access = Access.query.filter(Access.experiment == exp).filter(Access.user == user_).first()
                    if privilege and access:
                        access.privilege = privilege
                    elif privilege and not access:
                        Access(experiment=exp, user=user_, privilege=privilege)
                    elif access: # and not privilege
                        access.delete()
            if not success: break
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
        for ds in user.datasets(epoch_id):
            if (ds.kind != u'primary' and ds.kind != u'secondary') or user.has_access_to(ds, u'Read-Only'):
                dataset_data_list.append((ds.label + ('*' if ds.kind == u'primary' else ''),))
                dataset_attr_list.append({'id':'dataset=%d' % ds.id, 'class':'%s' % ('trash' if ds.trashtime else '')})
        return (dataset_data_list, dataset_attr_list)
