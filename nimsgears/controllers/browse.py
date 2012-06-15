from tg import config, expose, flash, redirect, request, response, require, session
from nimsgears.model import *
from nimsgears.controllers.nims import NimsController
from repoze.what import predicates

import json # return raw json to browser in cases of database queries
import transaction

class BrowseController(NimsController):
    @expose('nimsgears.templates.browse')
    def index(self):
        user = request.identity['user']

        # Table columns and their relevant classes
        exp_columns = [('Group', 'col_sunet'), ('Experiment', 'col_exp')]
        session_columns = [('Subj. Code', 'col_subj'), ('Date & Time', 'col_datetime')]
        epoch_columns = [('Time', 'col_time'), ('Description', 'col_desc')]
        dataset_columns = [('Data Type', 'col_type')]

        return dict(page='browse',
                    exp_columns=exp_columns,
                    session_columns=session_columns,
                    epoch_columns=epoch_columns,
                    dataset_columns=dataset_columns,
                    )

    @expose()
    def set_trash_flag(self, **kwargs):
        user = request.identity['user']
        result = {}
        if 'trash_flag' in kwargs:
            try:
                trash_flag = int(kwargs['trash_flag'])
            except:
                result['success'] = False
            else:
                session[user.uid] = trash_flag
                session.save()
                result['success'] = True
        else:
            result['success'] = False
        return json.dumps(result)

    @expose()
    def list_query(self, **kwargs):
        """ Return info about sessions for given experiment id."""
        user = request.identity['user']

        result = {}
        data_list, attr_list = [], []
        if 'dataset_list' in kwargs:
            try:
                epoch_id = int(kwargs['dataset_list'])
            except:
                result['success'] = False
            else:
                data_list, attr_list = self.get_datasets(user, epoch_id)
                result['success'] = True
        elif 'epoch_list' in kwargs:
            try:
                sess_id = int(kwargs['epoch_list'])
            except:
                result['success'] = False
            else:
                data_list, attr_list = self.get_epochs(user, sess_id)
                result['success'] = True
        elif 'sess_list' in kwargs:
            try:
                exp_id = int(kwargs['sess_list'])
            except:
                result['success'] = False
            else:
                data_list, attr_list = self.get_sessions(user, exp_id)
                result['success'] = True
        elif 'exp_list' in kwargs:
            data_list, attr_list = self.get_experiments(user)
            result['success'] = True
        else:
            result['success'] = False

        result['data'], result['attrs'] = data_list, attr_list

        return json.dumps(result)

    @expose()
    def trash(self, **kwargs):
        user = request.identity['user']
        id_list = query_type = db_query = None
        if "exp" in kwargs:
            id_list = kwargs["exp"]
            query_type = Experiment
            db_query = Experiment.query
        elif "sess" in kwargs:
            id_list = kwargs["sess"]
            query_type = Session
            db_query = (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        elif "epoch" in kwargs:
            id_list = kwargs["epoch"]
            query_type = Epoch
            db_query = (Epoch.query
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        elif "dataset" in kwargs:
            id_list = kwargs["dataset"]
            query_type = Dataset
            db_query = (Dataset.query
                .join(Epoch)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        db_query = db_query.join(Access).join(AccessPrivilege)

        result = {'success': False}
        if id_list and query_type and db_query:
            if isinstance(id_list, list):
                id_list = [int(item) for item in id_list]
            else:
                id_list = [id_list]

            db_query = db_query.filter(query_type.id.in_(id_list))

            if not (predicates.in_group('superusers') and user.admin_mode):
                mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
                db_query = db_query.filter(Access.user == user).filter(AccessPrivilege.value >= mg_privilege.value)

            db_result = db_query.all()

            # Verify that we still have all of the requested items after access
            # filtering
            if len(db_result) == len(id_list):
                result['success'] = True
                result['untrashed'] = False
                all_trash = True
                for db_item in db_result:
                    if all_trash and db_item.trashtime == None:
                        all_trash = False
                if not all_trash:
                    for db_item in db_result:
                        db_item.trash()
                else:
                    for db_item in db_result:
                        db_item.untrash()
                    result['untrashed'] = True
                transaction.commit()

        return json.dumps(result)

    @expose()
    def transfer_sessions(self, **kwargs):
        """ Queries DB given info found in POST
        """
        user = request.identity['user']

        sess_id_list = exp_id = None
        if "sess_id_list" in kwargs:
            sess_id_list = kwargs["sess_id_list"]
            if isinstance(sess_id_list, list):
                sess_id_list = [int(item) for item in kwargs["sess_id_list"]]
            else:
                sess_id_list = [sess_id_list]
        if "exp_id" in kwargs:
            exp_id = int(kwargs["exp_id"])

        result = {'success': False}

        if sess_id_list and exp_id:
            mg_privilege = AccessPrivilege.query.filter_by(name=u'mg').first()
            exp = DBSession.query(Experiment).filter_by(id = exp_id).one()
            db_query = DBSession.query(Session).join(Subject, Session.subject).join(Experiment, Subject.experiment).join(Access).join(AccessPrivilege).filter(Session.id.in_(sess_id_list))
            if not (predicates.in_group('superusers') and user.admin_mode):
                db_query = db_query.filter(Access.user == user).filter(AccessPrivilege.value >= mg_privilege.value)
            db_result_sess = db_query.all()

            # Verify that we still have all of the requested sessions after access filtering
            if len(db_result_sess) == len(sess_id_list):
                result['success'] = True
                result['untrashed'] = False
                all_trash = True
                for session in db_result_sess:
                    session.subject.experiment = exp
                    if all_trash and session.trashtime == None:
                        all_trash = False
                if not all_trash:
                    if session.subject.experiment.trashtime != None:
                        session.subject.experiment.untrash()
                        result['untrashed'] = True

                transaction.commit()

        return json.dumps(result)

    def get_popup_data_experiment(self, user, id_):
        db_query = Experiment.query.filter_by(id=id_)
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'experiment',
            'name': db_result.name
            } if db_result else None

    def get_popup_data_session(self, user, id_):
        db_query = (Session.query.filter_by(id=id_)
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'session',
            'name': db_result.name
            } if db_result else None

    def get_popup_data_epoch(self, user, id_):
        db_query = (Epoch.query.filter_by(id=id_)
            .join(Session, Epoch.session)
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'epoch',
            'name': db_result.name
            } if db_result else None

    def get_popup_data_dataset(self, user, id_):
        db_query = (Dataset.query.filter_by(id=id_)
            .join(Epoch)
            .join(Session, Epoch.session)
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))
        db_query = self.filter_access(db_query, user)
        db_result = db_query.first()
        return {
            'type': 'dataset',
            'subtype': 'pyramid',
            'name': db_result.__class__.__name__,
            'url': 'http://cni.stanford.edu/nimsgears/data' + db_result.relpath,
            } if db_result else None

    @expose()
    def get_popup_data(self, **kwargs):
        user = request.identity['user']
        popup_data = {}
        if "exp_id" in kwargs:
            try:
                id_ = int(kwargs["exp_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_experiment(user, id_)

        elif "sess_id" in kwargs:
            try:
                id_ = int(kwargs["sess_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_session(user, id_)

        elif "epoch_id" in kwargs:
            try:
                id_ = int(kwargs["epoch_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_epoch(user, id_)

        elif "dataset_id" in kwargs:
            try:
                id_ = int(kwargs["dataset_id"])
            except:
                pass
            else:
                popup_data = self.get_popup_data_dataset(user, id_)

        if popup_data:
            popup_data.update({'success': True})
        else:
            popup_data = {'success': False}

        return json.dumps(popup_data)
