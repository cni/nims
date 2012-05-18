from tg import expose, flash, require, lurl, request, redirect
from nimsgears.model import *
from nimsgears.lib.base import BaseController
from repoze.what import predicates

class NimsController(BaseController):
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
