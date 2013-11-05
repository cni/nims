# @author:  Reno Bowen
#           Gunnar Schaefer
#           Sara Benito

from tg import expose, request
import json

import re
import sys
import numpy
import datetime

import nimsdata
from nimsgears.model import *
from nimsgears.controllers.nims import NimsController


def is_ascii(s):
    if bool(re.match(r'^[a-zA-Z0-9-_<>\s\%]+$', s)):
        return True
    else:
        return False

def is_date(s):
    if bool(re.compile(r'\s*\d+\d+').match(s)):
        return True
    else:
        return False

def query_psdname(db_query, query_value):
    if not is_ascii(query_value):
        raise Exception
    return db_query.filter(Epoch.psd.ilike(query_value))

def query_scantype(db_query, query_value):
    return db_query.filter(Epoch.scan_type.ilike(query_value))

def query_subjectname(db_query, query_value):
    if not is_ascii(query_value):
        raise Exception
    return db_query.filter(Subject.lastname.ilike(query_value) | Subject.firstname.ilike(query_value))

def query_exam(db_query, query_value):
    return db_query.filter(Session.exam == int(query_value))

def query_operator(db_query, query_value):
    if not is_ascii(query_value):
        raise Exception
    user = User.get_by(uid=query_value)
    return db_query.filter(Session.operator == user)

def query_date_from(db_query, query_value):
    if not is_date(query_value):
        raise Exception
    return db_query.filter(Session.timestamp >= query_value)

def query_date_to(db_query, query_value):
    if not is_date(query_value):
        raise Exception
    return db_query.filter(Session.timestamp <= query_value)

def query_age_min(db_query, query_value):
    age = float(query_value)
    return db_query.filter(Session.timestamp - Subject.dob >= datetime.timedelta(days=age*365.25))

def query_age_max(db_query, query_value):
    age = float(query_value)
    if '.' not in query_value:  # user did not enter decimal value
        age += 1                # use intuitive range
    return db_query.filter(Session.timestamp - Subject.dob <= datetime.timedelta(days=age*365.25))

query_functions = {
        'subject_firstname' : query_subjectname,
        'subject_lastname' : query_subjectname,
        'search_exam' : query_exam,
        'search_operator' : query_operator,
        'search_age_min' : query_age_min,
        'search_age_max' : query_age_max,
        'search_psdname' : query_psdname,
        'search_scantype': query_scantype,
        'date_from': query_date_from,
        'date_to': query_date_to,
        }


class SearchController(NimsController):

    @expose('nimsgears.templates.search')
    def index(self):
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        dataset_cnt = Session.query.count()
        flag = user.is_superuser
        userdataset_cnt = user.dataset_cnt
        epoch_columns = [('Group', 'col_sunet'), ('Experiment', 'col_exp'), ('Date & Time', 'col_datetime'),
            ('Exam', 'col_exam'), ('Type Scan', 'col_scantype'), ('Description', 'col_desc')]
        dataset_columns = [('Data Type', 'col_type')]
        scantype_values = [''] + sorted(nimsdata.nimsimage.scan_types.all)
        psd_names_tuples = DBSession.query(Epoch.psd).distinct(Epoch.psd)
        psd_values = [''] + sorted([elem[0] for elem in psd_names_tuples])
        return dict(page='search',
            psd_values=psd_values,
            userdataset_cnt=userdataset_cnt,
            flag=flag,
            dataset_cnt=dataset_cnt,
            epoch_columns=epoch_columns,
            dataset_columns=dataset_columns,
            scantype_values=scantype_values)

    @expose()
    def query(self, **kwargs):
        result = {'success': False}
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        if not (
                'search_age_min' in kwargs and
                'search_age_max' in kwargs and
                'search_exam' in kwargs and
                'search_scantype' in kwargs and
                'search_operator' in kwargs and
                'search_psdname' in kwargs and
                'date_from' in kwargs and
                'date_to' in kwargs and
                (('subject_firstname' in kwargs and 'subject_lastname' in kwargs) or 'search_all' in kwargs) and
                not (
                    ('subject_firstname' in kwargs or 'subject_lastname' in kwargs)
                    and 'search_all' in kwargs
                    and not user.is_superuser
                    )
                ):
            return json.dumps(result)

        parameters = [(x.replace('*','%'), y) for x, y in kwargs.iteritems() if y and x != 'search_all']
        if not parameters:
            result = result = {'success': False, 'error_message' : 'empty_fields'}
            return json.dumps(result)

        db_query = (DBSession.query(Epoch, Session, Subject, Experiment)
                    .join(Session, Epoch.session)
                    .join(Subject, Session.subject)
                    .join(Experiment, Subject.experiment))
        if 'search_all' not in kwargs:
            db_query = db_query.join(Access, Experiment.accesses).filter(Access.user == user)
            if 'subject_firstname' in kwargs or 'subject_lastname' in kwargs:
                db_query = db_query.filter(Access.privilege >= AccessPrivilege.value(u'Read-Only'))
            else:
                db_query = db_query.filter(Access.privilege >= AccessPrivilege.value(u'Anon-Read'))

        for param, query in parameters:
            try:
                db_query = query_functions[param](db_query, query)
            except Exception as e:
                result = {'success': False, 'error_message' : 'Field "%s" = "%s" could not be processed: %s'
                                            % (param, query, e) }
                return json.dumps(result)

        data_list = []
        attr_list = []
        for res in db_query.all():
            data_list.append((res.Experiment.owner.gid,
                              res.Experiment.name,
                              res.Session.timestamp.strftime('%Y-%m-%d %H:%M'),
                              res.Session.exam,
                              res.Epoch.scan_type,
                              res.Epoch.description))
            attr_list.append({'id':'epoch=%d' % res.Epoch.id})

        result['data'] = data_list
        result['attrs'] = attr_list
        result['success'] = True
        return json.dumps(result)
