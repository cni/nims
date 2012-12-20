# @author:  Reno Bowen
#           Gunnar Schaefer

from tg import expose, request
from repoze.what import predicates
import transaction

import re
import datetime

from nimsgears.model import *
from nimsgears.controllers.nims import NimsController

import json


class SearchController(NimsController):

    @expose('nimsgears.templates.search')
    def index(self):
        dataset_cnt = Session.query.count()
        param_list = ['Subject Name', 'Subject Age', 'PSD Name', 'Exam', 'Operator']
        epoch_columns = [('Access', 'col_access'), ('Group', 'col_sunet'), ('Experiment', 'col_exp'), ('Date & Time', 'col_datetime'), ('Subj. Code', 'col_subj'), ('Description', 'col_desc')]
        dataset_columns = [('Data Type', 'col_type')]
        return dict(page='search',
            dataset_cnt=dataset_cnt,
            param_list=param_list,
            epoch_columns=epoch_columns,
            dataset_columns=dataset_columns)

    @expose()
    def query(self, **kwargs):
        # For more robust search query parsing, check out pyparsing.
        result = {}
        if 'search_param' in kwargs and 'search_query' in kwargs and 'date_from' in kwargs and 'date_to' in kwargs:
            search_query = kwargs['search_query'].replace('*', '%')
            if search_query==None:
                search_query = "*"
            db_query = DBSession.query(Epoch, Session, Subject, Experiment)
            if kwargs['search_param'] == 'PSD Name':
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .filter(Epoch.psd.ilike(search_query)))
            elif kwargs['search_param'] == 'Subject Name':
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .filter(Subject.lastname.ilike(search_query)))
            elif kwargs['search_param'] == 'Exam':
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .filter(Session.exam == int(search_query)))
            elif kwargs['search_param'] == 'Operator':
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .join(User)
                    .filter(User.uid.ilike(search_query)))
            elif kwargs['search_param'] == 'Subject Age':
                # TODO: allow more flexibility in age searches. E.g., "34", "34y", "408m", "=34", ">30", "<40", ">30y and <450m", "30 to 40", etc.
                min_age = None
                max_age = None
                a = re.match(r"\s*>(\d+)\s*<(\d+)|\s*>(\d+)|\s*(\d+)\s*to\s*(\d+)|\s*>(\d+)|\s*(\d+)", search_query)
                if a != None:
                    min_age = max(a.groups()[0:1]+a.groups()[2:4])
                    max_age = max(a.groups()[1:2]+a.groups()[4:5])
                    if min_age==None and max_age==None:
                        min_age = a.groups()[6]
                        max_age = a.groups()[6]
                if min_age==None:
                    min_age = 0
                if max_age==None:
                    max_age = 999999999
                db_query = (db_query
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment)
                    .filter(Session.timestamp - Subject.dob >= datetime.timedelta(days=float(min_age)*365.25))
                    .filter(Session.timestamp - Subject.dob <= datetime.timedelta(days=float(max_age)*365.25)))

            if kwargs['date_from'] != None and re.match(r'\s*\d+\d+',kwargs['date_from'])!=None:
                db_query = db_query.filter(Session.timestamp >= kwargs['date_from'])
            if kwargs['date_to'] != None and re.match(r'\s*\d+\d+',kwargs['date_to'])!=None:
                db_query = db_query.filter(Session.timestamp <= kwargs['date_to'])

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
            attr_list.append({'id':'epoch=%d' % epoch.id})
        return data_list, attr_list
