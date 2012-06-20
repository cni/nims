# @author:  Reno Bowen
#           Gunnar Schaefer

from tg import expose, request
from repoze.what import predicates
import transaction

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController

import json


class SearchController(NimsController):

    @expose('nimsgears.templates.search')
    def index(self):
        dataset_cnt = Session.query.count()
        param_list = ['Subject Name', 'PSD Name']
        epoch_columns = [('Access', 'col_access'), ('Group', 'col_sunet'), ('Experiment', 'col_exp'), ('Date & Time', 'col_datetime'), ('Subj. Code', 'col_subj'), ('Description', 'col_desc')]
        dataset_columns = [('Data Type', 'col_type')]
        return dict(page='search',
            dataset_cnt=dataset_cnt,
            param_list=param_list,
            epoch_columns=epoch_columns,
            dataset_columns=dataset_columns)

    @expose()
    def query(self, **kwargs):
        result = {}
        if 'search_param' in kwargs and 'search_query' in kwargs:
            db_query = None
            search_query = kwargs['search_query'].replace('*', '%')
            if kwargs['search_param'] == 'PSD Name':
                db_query = DBSession.query(Epoch, Session, Subject, Experiment)
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(Dataset, Epoch.datasets)
                    .filter(Dataset.psd.ilike(search_query)))
            elif kwargs['search_param'] == 'Subject Name':
                db_query = DBSession.query(Epoch, Session, Subject, Experiment)
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .filter(Subject.lastname.ilike(search_query)))
            if db_query:
                result['data'], result['attrs'] = self._process_result(db_query.all())
                result['success'] = True
            else:
                result['success'] = False
        else:
            result['success'] = False
        return json.dumps(result)

    def _process_result(self, db_result):
        data_list = []
        attr_list = []
        for value in db_result:
            exp = value.Experiment
            sess = value.Session
            subject = value.Subject
            epoch = value.Epoch
            data_list.append(('',
                              exp.owner.gid,
                              exp.name,
                              sess.timestamp.strftime('%Y-%m-%d %H:%M'),
                              subject.code,
                              epoch.description))
            attr_list.append({'id':'epoch_%d' % epoch.id})
        return data_list, attr_list
