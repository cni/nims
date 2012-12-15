# @author:  Reno Bowen

from tg import expose, request, session
from repoze.what import predicates
import transaction

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController
from nimsgears.widgets.experiment import EditExperimentForm

import json


class BrowseController(NimsController):

    @expose('nimsgears.templates.browse')
    def index(self):
        user = request.identity['user']

        # Table columns and their relevant classes
        exp_columns = [('Group', 'col_sunet'), ('Experiment', 'col_exp')]
        session_columns = [('Date & Time', 'col_datetime'), ('Subj. Code', 'col_subj')]
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
        db_query = db_query.join(Access)

        result = {'success': False}
        if id_list and query_type and db_query:
            if not isinstance(id_list, list):
                id_list = [id_list]

            db_query = db_query.filter(query_type.id.in_(id_list))

            if not user.is_superuser:
                db_query = db_query.filter(Access.user == user).filter(Access.privilege >= AccessPrivilege.value(u'Manage'))

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
            exp = Experiment.get(exp_id)
            db_query = Session.query.join(Subject, Session.subject).join(Experiment, Subject.experiment).join(Access).filter(Session.id.in_(sess_id_list))
            if not user.is_superuser:
                db_query = db_query.filter(Access.user == user).filter(Access.privilege >= AccessPrivilege.value(u'Manage'))
            db_result_sess = db_query.all()

            # Verify that we still have all of the requested sessions after access filtering
            if len(db_result_sess) == len(sess_id_list):
                result['success'] = True
                result['untrashed'] = False
                all_trash = True
                for session in db_result_sess:
                    session.move_to_experiment(exp)
                    if all_trash and session.trashtime == None:
                        all_trash = False
                if not all_trash:
                    if session.subject.experiment.trashtime != None:
                        session.subject.experiment.untrash()
                        result['untrashed'] = True

                transaction.commit()

        return json.dumps(result)
