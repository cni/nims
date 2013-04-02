# @author:  Reno Bowen

from tg import expose, request, session
import transaction
import json

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController
from nimsgears.widgets.experiment import EditExperimentForm


class BrowseController(NimsController):

    @expose('nimsgears.templates.browse')
    def index(self):
        return dict(
                page='browse',
                exp_columns=[('Group', 'col_sunet'), ('Experiment', 'col_exp')],
                session_columns=[('Date & Time', 'col_datetime'), ('Subj. Code', 'col_subj')],
                epoch_columns=[('Time', 'col_time'), ('Description', 'col_desc')],
                dataset_columns=[('Data Type', 'col_type')],
                )

    @expose()
    def trash_flag(self, **kwargs):
        return json.dumps(request.identity['user'].trash_flag if request.identity else 0)

    @expose()
    def set_trash_flag(self, **kwargs):
        user = request.identity['user']
        try:
            trash_flag = int(kwargs['trash_flag'])
            user.trash_flag = trash_flag
            success = True
        except:
            success = False
        return json.dumps({'success': success})

    @expose()
    def list_query(self, **kwargs):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        result = {}
        if 'exp_list' in kwargs:
            result['data'], result['attrs'] = self.get_experiments(user)
            result['success'] = True
        elif 'sess_list' in kwargs:
            result['data'], result['attrs'] = self.get_sessions(user, kwargs['sess_list'])
            result['success'] = True
        elif 'epoch_list' in kwargs:
            result['data'], result['attrs'] = self.get_epochs(user, kwargs['epoch_list'])
            result['success'] = True
        elif 'dataset_list' in kwargs:
            result['data'], result['attrs'] = self.get_datasets(user, kwargs['dataset_list'])
            result['success'] = True
        else:
            result['data'], result['attrs'] = [], []
            result['success'] = False
        return json.dumps(result)

    @expose()
    def trash(self, **kwargs):
        user = request.identity['user']
        if 'exp' in kwargs:
            id_list = kwargs['exp'] if isinstance(kwargs['exp'], list) else [kwargs['exp']]
            db_results = Experiment.query.filter(Experiment.id.in_(id_list)).all()
        elif 'sess' in kwargs:
            id_list = kwargs['sess'] if isinstance(kwargs['sess'], list) else [kwargs['sess']]
            db_results = Session.query.filter(Session.id.in_(id_list)).all()
        elif 'epoch' in kwargs:
            id_list = kwargs['epoch'] if isinstance(kwargs['epoch'], list) else [kwargs['epoch']]
            db_results = Epoch.query.filter(Epoch.id.in_(id_list)).all()
        elif 'dataset' in kwargs:
            id_list = kwargs['dataset'] if isinstance(kwargs['dataset'], list) else [kwargs['dataset']]
            db_results = Dataset.query.filter(Dataset.id.in_(id_list)).all()
        else:
            db_results = None
        result = {'success': False}
        if db_results and all([user.has_access_to(datum, u'Read-Write') for datum in db_results]):
            if any([(datum.trashtime is None) for datum in db_results]):    # trashing
                result['untrashed'] = True
                for datum in db_results:
                    datum.trash()
            else:                                                           # untrashing
                result['untrashed'] = True
                for datum in db_results:
                    datum.untrash()
            result['success'] = True
            transaction.commit()
        else:
            transaction.abort()
        return json.dumps(result)

    @expose()
    def transfer_sessions(self, **kwargs):
        user = request.identity['user']
        if 'sess_id_list' in kwargs:
            sess_ids = kwargs['sess_id_list'] if isinstance(kwargs['sess_id_list'], list) else [kwargs['sess_id_list']]
        sessions = Session.query.filter(Session.id.in_(sess_ids))
        exp = Experiment.get(kwargs.get('exp_id'))
        result = {'success': False, 'untrashed': False}
        if sessions and exp and all([user.has_access_to(s, u'Read-Write') for s in sessions]) and user.has_access_to(exp, u'Read-Write'):
            for sess in sessions:
                sess.move_to_experiment(exp)
            if exp.trashtime is not None and any([(sess.trashtime is None) for sess in sessions]):
                exp.untrash(propagate=False)
                result['untrashed'] = True
            result['success'] = True
            transaction.commit()
        else:
            transaction.abort()
        return json.dumps(result)
