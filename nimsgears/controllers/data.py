# -*- coding: utf-8 -*-
"""Sample controller with all its actions protected."""
from tg import config, expose, flash, redirect, request, require
from tg.i18n import ugettext as _, lazy_ugettext as l_
from repoze.what import predicates
from tgext.admin.controller import AdminController
from tgext.admin.tgadminconfig import TGAdminConfig

from collections import OrderedDict

from nimsgears import model
from nimsgears.model import *

from nimsgears.lib.base import BaseController

import nimsutil

import json # return raw json to browser in cases of database queries
import transaction

__all__ = ['DataController', 'PublicDataController']


class NimsAdminConfig(TGAdminConfig):
    default_index_template = 'genshi:nimsgears.templates.tg_admin'


class NimsAdminController(AdminController):
    allow_only = predicates.in_group('superusers')


class DataController(BaseController):

    def index(self):
        redirect('/pub/browse')

    @expose()
    def browse(self, **kwargs):
        return dict(page='browse')

class AuthDataController(DataController):

    tg_admin = NimsAdminController(model, DBSession, NimsAdminConfig)

    allow_only = predicates.not_anonymous(msg=l_('You must be logged in to view this page.'))

    # FIXME: handle deactivated users
    #active_user = predicates.in_group('users', msg=l_('Your account is inactive. You can request activation below.'))

    def _not_active_user(msg):
        flash(msg)
        redirect('/auth/activate')

    @expose()
    def index(self):
        redirect('/auth/status')

    @expose('nimsgears.templates.activate')
    def activate(self, **kwargs):
        return self.prefs()

    @expose('nimsgears.templates.toggle_admin')
    def toggle_admin(self, came_from):
        user = request.identity['user']
        DBSession.add(user)
        user.admin_mode = not user.admin_mode
        redirect(came_from)

    @expose('nimsgears.templates.prefs')
    def prefs(self, **kwargs):
        user = request.identity['user']

        if kwargs:
            DBSession.add(user)
            for key, value in kwargs.iteritems():
                setattr(user, key, value)
            flash(l_('Your settings have been updated.'))

        if not user.name or not user.email:
            ldap_name, ldap_email = nimsutil.ldap_query(user.uid)
        name = user.name or ldap_name
        email = user.email or ldap_email

        prefs = OrderedDict(
                name = ('Display Name', name),
                email = ('Email Address', email)
                )

        return dict(page='prefs', prefs=prefs)

    @expose('nimsgears.templates.status')
    def status(self):
        #if not predicates.in_group('active_users').is_met(request.environ):
        #    flash(l_('Your account is not yet active.'))
        #    redirect('/auth/prefs')
        return dict(page='status', params={})

    #@expose('nimsgears.templates.browse')
    #def browse(self, **kwargs):
    #    user = request.identity['user'] if request.identity else None

    #    columns = ['Date & Time', 'Group', 'Experiment', 'MRI Exam #', 'Subject Name']
    #    datatypes = ['Dicom', 'NIfTI', 'SPM NIfTI', 'k-Space']
    #    searchByOptions = ['Subject Name', 'Group'];

    #    query = DBSession.query(Session, Experiment, Subject, ResearchGroup)
    #    query = query.join(Experiment, Session.experiment)
    #    query = query.join(Subject, Session.subject)
    #    query = query.join(ResearchGroup, Experiment.owner)

    #    query = query.join(Access, Experiment.accesses)
    #    #query = query.filter(Access.user==user)

    #    if 'Subject Name' in kwargs and kwargs['Subject Name']:
    #        query_str = kwargs['Subject Name'].replace('*', '%')
    #        query = query.filter(Subject.lastname.ilike(query_str))

    #    if 'Group' in kwargs and kwargs['Group']:
    #        query_str = kwargs['Group'].replace('*', '%')
    #        query = query.filter(ResearchGroup.gid.ilike(query_str))

    #    results = query.all()

    #    sessiondata = [(r.Session.id, r.Session.timestamp.strftime('%Y-%m-%d %H:%M:%S'), r.Experiment.owner, r.Experiment, r.Session.mri_exam, r.Subject) for r in results]

    #    filter_info = {}
    #    experiments = sorted(set([r.Experiment for r in results]), key=lambda exp: exp.name)
    #    for exp in experiments:
    #        filter_info[exp.owner.gid] = filter_info.get(exp.owner.gid, []) + [exp.name]
    #    filter_info = sorted([(k,v) for k,v in filter_info.iteritems()], key=lambda tup: tup[0])

    #    return dict(page='browse', filter_info=filter_info, datatypes=datatypes, columns=columns, sessiondata=sessiondata, searchByOptions=searchByOptions)

    @expose('nimsgears.templates.search')
    def search(self):
        dataset_cnt = len(Session.query.all())
        return dict(page='search', dataset_cnt=dataset_cnt)

    @expose('nimsgears.templates.admin')
    def admin(self):
        return dict(page='admin', params={})

    @expose(content_type='image/png')
    def image(self, *args):
        return open('/tmp/image.png', 'r')

    @expose(content_type='application/x-tar')
    def download(self, *args, **kwargs):
        session_id = kwargs['session_id']
        query = DBSession.query(Dataset)
        query = query.join(Epoch, Dataset.epoch).join(Session, Epoch.session)
        results = query.filter(Session.id == session_id).all()

        paths = ' '.join([dataset.path for dataset in results])

        import shlex
        import subprocess as sp
        tar_proc = sp.Popen(shlex.split('tar -czf - %s' % paths), stdout=sp.PIPE, cwd=config.get('store_path'))
        ## tried this to get async pipe working with paster, but doesn't seem to do anything
        ## should work outright with apache once python bug is fixed: http://bugs.python.org/issue13156
        #import fcntl, os
        #fd = tar_proc.stdout.fileno()
        #file_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        #fcntl.fcntl(fd, fcntl.F_SETFL, file_flags | os.O_NDELAY)
        return tar_proc.stdout

    @expose()
    def session_query(self, **kwargs):
        """ Return info about sessions for given experiment id."""
        user = request.identity['user']

        def session_tuple(session, axs_priv_val):
            return (session.id, session.mri_exam, unicode(session.subject) if axs_priv_val != 0 else 'Anonymous')

        try:
            exp_id = int(kwargs['id'])
        except:
            exp_id = -1

        if predicates.in_group('superusers') and user.admin_mode:
            results = Session.query.join(Experiment).filter(Experiment.id==exp_id).all()
            sessions = [session_tuple(session, -1) for session in results]
        else:
            query = DBSession.query(Session, Access).join(Experiment).join(Access)
            results = query.filter(Experiment.id==exp_id).filter(Access.user==user).all()
            sessions = [session_tuple(result.Session, result.Access.privilege.value) for result in results]
        return json.dumps(sessions)

    @expose()
    def update_epoch(self, **kwargs):
        user = request.identity['user']

        try:
            epoch_id = int(kwargs['id'])
            desc = kwargs['desc']
        except:
            epoch_id = -1
            desc = None

        rw_privilege = AccessPrivilege.query.filter_by(name = u'rw').first()
        epoch = DBSession.query(Epoch).join('session', 'experiment', 'access', 'privilege').filter(Epoch.id == epoch_id).filter(Access.user == user).filter(AccessPrivilege.value > rw_privilege.value).first()

        if epoch:
            epoch.mri_desc = desc
            transaction.commit()
            success = True
        else:
            success = False

        return json.dumps({'success':success})

    @expose()
    def epoch_query(self, **kwargs):
        """ Queries DB given info found in POST, TODO perhaps verify access level another time here??
        """
        def summarize_epoch(epoch, sess_id):
            return (epoch.id, "%2d/%2d" % (epoch.mri_series, epoch.mri_acq), epoch.mri_desc)

        try:
            sess_id = int(kwargs['id'])
        except:
            sess_id = -1

        epoch_list = ([summarize_epoch(item.Epoch, sess_id) for item in
            DBSession.query(Epoch, Session).join('session').filter(Session.id == sess_id).all()])

        return json.dumps(epoch_list)

    @expose()
    def transfer_sessions(self, **kwargs):
        """ Queries DB given info found in POST, TODO perhaps verify access level another time here??
        """
        # STILL NEED TO IMPLEMENT ACCESS CHECKING TODO
        # FOR NOW, JUST TRANSFERRING WITHOUT A CHECK SO I CAN DEMONSTRATE CONCEPT FIXME

        sess_id_list = kwargs["sess_id_list"]
        if isinstance(sess_id_list, list):
            sess_id_list = [int(item) for item in kwargs["sess_id_list"]]
        else:
            sess_id_list = [sess_id_list]
        print sess_id_list
        exp_id = int(kwargs["exp_id"])

        exp = DBSession.query(Experiment).filter_by(id = exp_id).one()
        sess_list = DBSession.query(Session).filter(Session.id.in_(sess_id_list)).all()
        for session in sess_list:
            session.experiment = exp

        transaction.commit()

        return json.dumps({"success":True})

    @expose('nimsgears.templates.browse')
    def browse(self):
        user = request.identity['user']

        exp_dict_dict = {}
        if predicates.in_group('superusers') and user.admin_mode:
            experiments = Experiment.query.all()
            exp_dict_dict[u'mg'] = dict([(exp.id, (exp.owner.gid, exp.name)) for exp in experiments])
        else:
            results = DBSession.query(Experiment, Access).join(Access).filter(Access.user == user).all()
            for exp, axs in results:
                exp_dict_dict.setdefault(axs.privilege.name, {})[exp.id] = (exp.owner.gid, exp.name)

        # FIXME i plan to replace these things with just column number
        # indicators computed in the front end code... keep class names out of back end
        exp_columns = [('Owner', 'col_sunet'), ('Experiment', 'col_name')]
        session_columns = [('Exam', 'col_exam'), ('Subject Name', 'col_sname')]
        epoch_columns = [('S/A', 'col_sa'), ('Description', 'col_desc')]

        return dict(page='browse',
                    exp_dict_dict=exp_dict_dict,
                    exp_columns=exp_columns,
                    session_columns=session_columns,
                    epoch_columns=epoch_columns)

    @expose('nimsgears.templates.groups')
    def groups(self):

        user_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name')]
        return dict(page='groups',
                    user_columns = user_columns,
                    )

    @expose('nimsgears.templates.access')
    def access(self):
        user = request.identity['user']

        exp_dict_dict = {} # exp_dict by access level
        access_levels = [u'mg']
        for access_level in access_levels:
            exp_dict = {} # exp by exp_id
            privilege = AccessPrivilege.query.filter_by(name=access_level).one()
            db_item_list = DBSession.query(Experiment, Access).join(Access).filter(Access.user == user).filter(Access.privilege == privilege).all()
            for db_item in db_item_list:
                exp = db_item.Experiment
                exp_dict[exp.id] = (exp.owner.gid, exp.name)
            exp_dict_dict[access_level] = exp_dict

        user_list = [(usr.uid, usr.name if usr.name else 'None') for usr in User.query.all()]

        # FIXME i plan to replace these things with just column number
        # indicators computed in the front end code... keep class names out of back end
        exp_columns = [('Owner', 'col_sunet'), ('Name', 'col_name')]
        user_columns = [('SUNetID', 'col_sunet'), ('Name', 'col_name')]

        access_levels.insert(0, u'pi')
        return dict(page='access',
                    user_list=user_list,
                    user_columns=user_columns,
                    exp_dict_dict=exp_dict_dict,
                    access_levels=access_levels,
                    exp_columns=exp_columns,
                    )
