# @author:  Reno Bowen

from tg import expose, request
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates

from nimsgears.model import *
from nimsgears.lib.base import BaseController

import json


class NimsController(BaseController):

    @expose()
    def get_trash_flag(self, **kwargs):
        user = request.identity['user']
        trash_flag = user.get_trash_flag()
        return json.dumps(trash_flag)

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

    def filter_access(self, db_query, user):
        db_query = db_query.join(Access)
        if not user.is_superuser:
            db_query = db_query.filter(Access.user == user).filter(Access.privilege >= AccessPrivilege.value(u'Manage'))
        return db_query

    def get_experiments(self, user, manage_only=False):
        exp_data_list = []
        exp_attr_list = []

        experiment_dict = user.get_experiments(with_privilege=(u'Manage' if manage_only else None))

        # if superuser, ignore access items and set all to manage
        for key, value in experiment_dict.iteritems():
            exp = value.Experiment
            acc_priv = u'Manage' if user.is_superuser else AccessPrivilege.name(value.Access.privilege)
            exp_data_list.append((exp.owner.gid, exp.name))
            exp_attr_list.append({'id':'exp=%d' % key, 'class':'access=%s %s' % (acc_priv.lower(), 'trash' if exp.trashtime else '')})
        return (exp_data_list, exp_attr_list)

    def get_sessions(self, user, exp_id):
        sess_data_list = []
        sess_attr_list = []

        session_dict = user.get_sessions(by_experiment_id=exp_id)
        for key, value in session_dict.iteritems():
            sess = value.Session
            sess_data_list.append((sess.timestamp.strftime('%Y-%m-%d %H:%M'), sess.subject.code))
            sess_attr_list.append({'id':'sess=%d' % key, 'class':'%s' % ('trash' if sess.trashtime else '')})
        return (sess_data_list, sess_attr_list)

    def get_datasets(self, user, epoch_id):
        dataset_data_list = []
        dataset_attr_list = []

        dataset_dict = user.get_datasets(by_epoch_id=epoch_id)
        for key, value in dataset_dict.iteritems():
            dataset = value.Dataset
            dataset_data_list.append((dataset.label + ('*' if dataset.kind == u'primary' else ''),))
            dataset_attr_list.append({'id':'dataset=%d' % key, 'class':'%s' % ('trash' if dataset.trashtime else '')})
        return (dataset_data_list, dataset_attr_list)

    def get_epochs(self, user, sess_id):
        epoch_data_list = []
        epoch_attr_list = []

        epoch_dict = user.get_epochs(by_session_id=sess_id)

        for key, value in epoch_dict.iteritems():
            epoch = value.Epoch
            epoch_data_list.append((epoch.timestamp.strftime('%H:%M:%S'), '%s' % epoch.description))
            epoch_attr_list.append({'id':'epoch=%d' % key, 'class':'%s' % ('trash' if epoch.trashtime else '')})
        return (epoch_data_list, epoch_attr_list)
