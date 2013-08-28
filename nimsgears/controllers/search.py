# @author:  Reno Bowen
#           Gunnar Schaefer

from tg import expose, request
import json

import re
import datetime
import sys

from nimsgears.model import *; import transaction
from nimsgears.controllers.nims import NimsController

def is_ascii(s):
    if bool(re.compile(r'^[\w\W\b\B\d\D\s\S]+$').match(s)):
        return True
    else:
        return False
    
def is_a_number(n):
    try:
        int(n)
        return True
    except ValueError:
        return False
        
def is_other_field(n):
    return True
    
            
validation_functions = {
    'Subject Name' : is_ascii,
    'Exam' : is_a_number,
    'Operator' : is_ascii,
    'Subject Age' : is_ascii,
    'PSD Name' : is_ascii,
    'Scan Type': is_ascii,
}

def query_psdname( db_query, query_value ):
    return db_query.filter(Epoch.psd.ilike( query_value ))
    
def query_scantype( db_query, query_value ):
    return db_query.filter(Epoch.scan_type.ilike( query_value ))
            
def query_subjectname( db_query, query_value ):
    return db_query.filter(Subject.lastname.ilike( query_value ) | Subject.firstname.ilike( query_value ))
        
def query_exam( db_query, query_value ):
    return db_query.filter(Session.exam == int( query_value ))
            
def query_operator( db_query, query_value ):
    return (db_query.join(User)
                    .filter(User.uid.ilike(query_value) | User.firstname.ilike( query_value ) | User.lastname.ilike( query_value )))
                    
def query_subjectage( db_query, query_value ):
    min_age = None
    max_age = None
    a = re.match(r"\s*>(\d+)\s*<(\d+)|\s*>(\d+)|\s*(\d+)\s*to\s*(\d+)|\s*<(\d+)|\s*(\d+)", query_value )
    if a != None:
        min_age = max(a.groups()[0:1]+a.groups()[2:4])
        max_age = max(a.groups()[1:2]+a.groups()[4:5])
        if min_age==None and max_age==None:
            min_age = a.groups()[6]
            max_age = a.groups()[6]
        if min_age==None:
            min_age = 0
        if max_age==None:
            max_age = 200
    return (db_query
            .filter(Session.timestamp - Subject.dob >= datetime.timedelta(days=float(min_age)*365.25))
            .filter(Session.timestamp - Subject.dob <= datetime.timedelta(days=float(max_age)*365.25)))
            
query_functions = {
    'Subject Name' : query_subjectname,
    'Exam' : query_exam,
    'Operator' : query_operator,
    'Subject Age' : query_subjectage,
    'PSD Name' : query_psdname,
    'Scan Type': query_scantype,
}


class SearchController(NimsController):

    @expose('nimsgears.templates.search')
    def index(self):
        dataset_cnt = Session.query.count()
        param_list = [ 'Subject Age', 'PSD Name', 'Exam', 'Operator', 'Scan Type']
        epoch_columns = [('Access', 'col_access'), ('Group', 'col_sunet'), ('Experiment', 'col_exp'), ('Date & Time', 'col_datetime'), ('Scan Type', 'col_typescan'), ('Description', 'col_desc')]
        dataset_columns = [('Data Type', 'col_type')]
        scantype_values = ['','anatomy', 'functional', 'calibration', 'localizer']
        return dict(page='search',
                dataset_cnt=dataset_cnt,
            param_list=param_list,
            epoch_columns=epoch_columns,
            dataset_columns=dataset_columns,
            scantype_values=scantype_values)
               
               
               
    @expose()
    def query(self, **kwargs):
        # For more robust search query parsing, check out pyparsing.
        result = {'success': False}
        print kwargs
        if 'search_param' in kwargs and 'search_query' in kwargs and 'date_from' in kwargs and 'date_to' in kwargs and 'subject_name' in kwargs:
            search_query = kwargs['search_query']
            search_param = kwargs['search_param']
            search_name = kwargs['subject_name']         
            for sn in search_name:
                search_query.append(sn)
                search_param.append('Subject Name')
        elif 'search_param' in kwargs and 'search_query' in kwargs and 'date_from' in kwargs and 'date_to' in kwargs and 'choose_db' in kwargs:
            search_query = kwargs['search_query']
            search_param = kwargs['search_param']
        else:
            return json.dumps(result)

        if isinstance(search_query, basestring): search_query = [ search_query ]
        if isinstance(search_param, basestring): search_param = [ search_param ]
        
        
        search_query = [x.replace('*','%') for x in search_query]
        
        #Zip fields and if any field is empty remove it from parameters
        parameters = [(x,y) for x,y in zip(search_param, search_query) if y]
        
        user = request.identity['user'] if request.identity else User.get_by(uid=u'@public')
        
        
        if 'choose_db' in kwargs:
            parameters = [(x,y) for x,y in parameters if x != 'Subject Name']
            db_query = (DBSession.query(Epoch, Session, Subject, Experiment)
                        .join(Session, Epoch.session)
                        .join(Subject, Session.subject)
                        .join(Experiment, Subject.experiment))
        else:
            db_query = (DBSession.query(Epoch, Session, Subject, Experiment)
                        .join(Session, Epoch.session)
                        .join(Subject, Session.subject)
                        .join(Experiment, Subject.experiment)
                        .join(Access,Experiment.accesses)
                        .filter(Access.user == user))
            for elem in parameters:
                if 'Subject Name' in elem[0]:
                    db_query = db_query.filter(Access.privilege >= AccessPrivilege.value(u'Read-Only'))
                else:
                    db_query = db_query.filter(Access.privilege >= AccessPrivilege.value(u'Anon-Read'))
            
        # TODO: when fields are all empty stop the search.
        if len(parameters)==0 and kwargs['date_from']=='' and kwargs['date_to']=='':
            return json.dumps(result)

        
        for param, query in parameters:
            if not validation_functions[param](query):
                # The query value is not valid
                result = {'success': False, 'error_message' : 'Field ' + query + 'could not be processed'}
                return json.dumps(result)
            db_query = query_functions[param](db_query, query)
        
        if kwargs['date_from'] != None and re.match(r'\s*\d+\d+',kwargs['date_from'])!=None:
            db_query = db_query.filter(Session.timestamp >= kwargs['date_from'])
        if kwargs['date_to'] != None and re.match(r'\s*\d+\d+',kwargs['date_to'])!=None:
            db_query = db_query.filter(Session.timestamp <= kwargs['date_to'])

        result['data'], result['attrs'] = self._process_result(db_query.all())
        result['success'] = True
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
                              epoch.scan_type,
                              epoch.description))
            attr_list.append({'id':'epoch=%d' % epoch.id})
        return data_list, attr_list
