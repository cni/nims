import os
import re
import shutil
import hashlib
import datetime

import transaction
from elixir import *

import nimsutil
from nimsgears.model import metadata, DBSession
from repoze.what import predicates

from tg import session
from sqlalchemy.util._collections import NamedTuple

__session__ = DBSession
__metadata__ = metadata

__all__  = ['Group', 'User', 'Permission', 'Message', 'Job', 'Access', 'AccessPrivilege']
__all__ += ['ResearchGroup', 'Person', 'Subject', 'DataContainer', 'Experiment', 'Session', 'Epoch', 'Dataset']


class Group(Entity):

    """Group definition for :mod:`repoze.what`; `group_name` required."""

    gid = Field(Unicode(32), unique=True)           # translation for group_name set in app_cfg.py
    name = Field(Unicode(255))
    created = Field(DateTime, default=datetime.datetime.now)

    users = ManyToMany('User', onupdate='CASCADE', ondelete='CASCADE')
    permissions = ManyToMany('Permission', onupdate='CASCADE', ondelete='CASCADE')

    def __repr__(self):
        return ('<Group: group_id=%s>' % self.gid).encode('utf-8')

    def __unicode__(self):
        return self.name

    @classmethod
    def by_gid(cls, gid):
        return cls.query.filter_by(gid=gid).one()


class User(Entity):

    """User definition for :mod:`repoze.who`; `user_name` required."""

    uid = Field(Unicode(32), unique=True)           # translation for user_name set in app_cfg.py
    firstname = Field(Unicode(255))
    lastname = Field(Unicode(255))
    email = Field(Unicode(255))
    _password = Field(Unicode(128), colname='password', synonym='password')
    created = Field(DateTime, default=datetime.datetime.now)
    admin_mode = Field(Boolean, default=False)

    groups = ManyToMany('Group', onupdate='CASCADE', ondelete='CASCADE')

    accesses = OneToMany('Access')
    research_groups = ManyToMany('ResearchGroup', inverse='members')
    manager_groups = ManyToMany('ResearchGroup', inverse='managers')
    pi_groups = ManyToMany('ResearchGroup', inverse='pis')
    messages = OneToMany('Message', inverse='recipient')

    def __init__(self, **kwargs):
        if 'uid' in kwargs:
            ldap_firstname, ldap_lastname, ldap_email = nimsutil.ldap_query(kwargs['uid'])
            kwargs['firstname'] = ldap_firstname
            kwargs['lastname'] = ldap_lastname
            kwargs['email'] = ldap_email
        super(User, self).__init__(**kwargs)

    def __repr__(self):
        return (u'<User: %s, %s, %s>' % (self.uid, self.email, self.name)).encode('utf-8')

    def __unicode__(self):
        return self.name or self.uid

    @property
    def name(self):
        if self.firstname and self.lastname:
            return u'%s, %s' % (self.lastname, self.firstname)
        else:
            return self.lastname

    @property
    def displayname(self):
        if self.firstname and self.lastname:
            return u'%s %s' % (self.firstname, self.lastname)
        else:
            return self.uid

    @property
    def is_superuser(self):
        """Return True if user is a superuser and has admin mode enabled."""
        return predicates.in_group('superusers') and self.admin_mode

    @classmethod
    def by_email(cls, email):
        return cls.query.filter_by(email=email).first()

    @classmethod
    def by_uid(cls, uid, create=False, password=None):
        user = cls.query.filter_by(uid=uid).first()
        if not user and create:
            user = cls(uid=uid, password=(password or uid))
        return user

    @staticmethod
    def _hash_password(password):
        # Make sure password is a str because we cannot hash unicode objects
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        salt = hashlib.sha256()
        salt.update(os.urandom(60))
        hash = hashlib.sha256()
        hash.update(password + salt.hexdigest())
        password = salt.hexdigest() + hash.hexdigest()
        # Make sure the hashed password is a unicode object at the end of the
        # process because SQLAlchemy _wants_ unicode objects for Unicode cols
        if not isinstance(password, unicode):
            password = password.decode('utf-8')
        return password

    def _set_password(self, password):
        """Hash ``password`` on the fly and store its hashed version."""
        self._password = self._hash_password(password)
    def _get_password(self):
        """Return the hashed version of the password."""
        return self._password
    password = property(_get_password, _set_password)

    def validate_password(self, password):
        """Check the password against existing credentials."""
        hash = hashlib.sha256()
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        hash.update(password + str(self.password[:64]))
        return self.password[64:] == hash.hexdigest()

    @property
    def permissions(self):
        """Return a set with all permissions granted to the user."""
        perms = set()
        for g in self.groups:
            perms = perms | set(g.permissions)
        return perms

    @property
    def unread_msg_cnt(self):
        return len([msg for msg in self.messages if not msg.read]) if self.messages else 0

    @property
    def dataset_cnt(self):
        query = DBSession.query(Session)
        if not self.is_superuser:
            query = query.join(Subject, Session.subject).join(Experiment, Subject.experiment).join(Access).filter(Access.user==self)
        return query.count()

    @property
    def job_cnt(self):
        return Job.query.filter((Job.status == u'pending') | (Job.status == u'running')).count()

    def get_trash_flag(self):
        trash_flag = session.get(self.uid, 0)
        return trash_flag

    def _filter_query(self, query, with_privilege=None):
        query = query.add_entity(Access).join(Access).filter(Access.user == self)
        if with_privilege:
            query = query.filter(Access.privilege >= AccessPrivilege.value(with_privilege))
        return query

    def has_access_to(self, element, with_privilege=None):
        if isinstance(element, Experiment):
            query = Experiment.query
        elif isinstance(element, Session):
            query = (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        elif isinstance(element, Epoch):
            query = (Epoch.query
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        elif isinstance(element, Dataset):
            query = (Dataset.query
                .filter(Dataset.id == element.id)
                .join(Epoch)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))
        else:
            return False
        result = self._filter_query(query, with_privilege).first()
        return result != None


    def get_experiments(self, including_trash=None, only_trash=None, contains_trash=None, with_privilege=None):
        if not (including_trash or only_trash or contains_trash):
            trash_flag = self.get_trash_flag()
            if trash_flag == 1:
                including_trash = True
            elif trash_flag == 2:
                contains_trash = True

        query = Experiment.query

        if including_trash:
            pass # including everything, so no filter necessary
        elif only_trash or contains_trash:
            query = (query
                .join(Subject, Experiment.subjects)
                .join(Session, Subject.sessions)
                .join(Epoch, Session.epochs)
                .join(Dataset, Epoch.datasets))
            if only_trash:
                query = (query
                    .filter(Experiment.trashtime != None))
            else: # contains_trash
                query = (query
                    .filter((Experiment.trashtime != None) |
                            (Session.trashtime != None) |
                            (Epoch.trashtime != None) |
                            (Dataset.trashtime != None)))
        else: # no trash
            query = (query
                .filter(Experiment.trashtime == None))

        result_dict = {}
        if self.is_superuser:
            unfiltered_results = query.all()
            for result in unfiltered_results:
                result_dict[result.id] = result

        filtered_results = self._filter_query(query, with_privilege).all()
        for result in filtered_results:
            result_dict[result.Experiment.id] = result

        # Since these don't hit the filter, and thus don't get access privileges appended to them, we add them here
        if self.is_superuser:
            for key, value in result_dict.iteritems():
                if not isinstance(value, NamedTuple):
                    result_dict[key] = NamedTuple([value, None], ['Experiment', 'Access'])

        return result_dict

    def get_sessions(self, by_experiment_id=None, including_trash=False, only_trash=False, contains_trash=False, with_privilege=None):
        if not (including_trash or only_trash or contains_trash):
            trash_flag = self.get_trash_flag()
            if trash_flag == 1:
                including_trash = True
            elif trash_flag == 2:
                contains_trash = True

        query = (Session.query
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))

        if by_experiment_id:
            query = (query
                .filter(Experiment.id == by_experiment_id))

        if including_trash:
            pass # including everything, so no filter necessary
        elif contains_trash or only_trash:
            query = (query
                .join(Epoch, Session.epochs)
                .join(Dataset, Epoch.datasets))
            if only_trash:
                query = (query
                    .filter(Session.trashtime != None))
            else: # contains_trash
                query = (query
                    .filter((Session.trashtime != None) |
                            (Epoch.trashtime != None) |
                            (Dataset.trashtime != None)))
        else: # no trash
            query = (query
                .filter(Session.trashtime == None))

        result_dict = {}
        if self.is_superuser:
            unfiltered_results = query.all()
            for result in unfiltered_results:
                result_dict[result.id] = result

        filtered_results = self._filter_query(query, with_privilege).all()
        for result in filtered_results:
            result_dict[result.Session.id] = result

        # Since these don't hit the filter, and thus don't get access
        # privileges appended to them, we add them
        if self.is_superuser:
            for key, value in result_dict.iteritems():
                if not isinstance(value, NamedTuple):
                    result_dict[key] = NamedTuple([value, None], ['Session', 'Access'])

        return result_dict

    def get_epochs(self, by_experiment_id=None, by_session_id=None, including_trash=False, only_trash=False, contains_trash=False, with_privilege=None):
        if not (including_trash or only_trash or contains_trash):
            trash_flag = self.get_trash_flag()
            if trash_flag == 1:
                including_trash = True
            elif trash_flag == 2:
                contains_trash = True

        query = (Epoch.query
            .join(Session, Epoch.session))

        if by_session_id:
            query = (query
                .filter(Session.id == by_session_id))

        query = (query
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))

        if by_experiment_id:
            query = (query
                .filter(Experiment.id == by_experiment_id))

        if including_trash:
            pass # including everything, so no filter necessary
        elif only_trash or contains_trash:
            query = (query
                .join(Dataset, Epoch.datasets))
            if only_trash:
                query = (query
                    .filter(Epoch.trashtime != None))
            else: # contains_trash
                query = (query
                    .filter((Epoch.trashtime != None) |
                            (Dataset.trashtime != None)))
        else: # no trash
            query = (query
                .filter(Epoch.trashtime == None))

        result_dict = {}
        if self.is_superuser:
            unfiltered_results = query.all()
            for result in unfiltered_results:
                result_dict[result.id] = result

        filtered_results = self._filter_query(query, with_privilege).all()
        for result in filtered_results:
            result_dict[result.Epoch.id] = result

        # Since these don't hit the filter, and thus don't get access
        # privileges appended to them, we add them
        if self.is_superuser:
            for key, value in result_dict.iteritems():
                if not isinstance(value, NamedTuple):
                    result_dict[key] = NamedTuple([value, None], ['Epoch', 'Access'])

        return result_dict

    def get_datasets(self, by_experiment_id=None, by_session_id=None, by_epoch_id=None, including_trash=False, only_trash=False, contains_trash=False, with_privilege=None):
        if not (including_trash or only_trash or contains_trash):
            trash_flag = self.get_trash_flag()
            if trash_flag == 1:
                including_trash = True
            elif trash_flag == 2:
                contains_trash = True

        query = (Dataset.query
            .join(Epoch))

        if by_epoch_id:
            query = (query
                .filter(Epoch.id == by_epoch_id))

        query = (query
            .join(Session, Epoch.session))

        if by_session_id:
            query = (query
                .filter(Session.id == by_session_id))

        query = (query
            .join(Subject, Session.subject)
            .join(Experiment, Subject.experiment))

        if by_experiment_id:
            query = (query
                .filter(Experiment.id == by_experiment_id))

        if including_trash:
            pass # including everything, so no filter necessary
        elif only_trash or contains_trash:
            query = (query
                .filter(Dataset.trashtime != None))
        else: # no trash
            query = (query
                .filter(Dataset.trashtime == None))

        result_dict = {}
        if self.is_superuser:
            unfiltered_results = query.all()
            for result in unfiltered_results:
                result_dict[result.id] = result

        filtered_results = self._filter_query(query, with_privilege).all()
        for result in filtered_results:
            result_dict[result.Dataset.id] = result

        # Since these don't hit the filter, and thus don't get access
        # privileges appended to them, we add them
        if self.is_superuser:
            for key, value in result_dict.iteritems():
                if not isinstance(value, NamedTuple):
                    result_dict[key] = NamedTuple([value, None], ['Dataset', 'Access'])

        return result_dict

class Permission(Entity):

    """Permission definition for :mod:`repoze.what`; `permission_name` required."""

    pid = Field(Unicode(32), unique=True)           # translation for user_name set in app_cfg.py
    name = Field(Unicode(255))

    groups = ManyToMany('Group', onupdate='CASCADE', ondelete='CASCADE')

    def __repr__(self):
        return ('<Permission: name=%s>' % self.pid).encode('utf-8')

    def __unicode__(self):
        return self.pid


class Message(Entity):

    subject = Field(Unicode(255), required=True)
    body = Field(Unicode)
    priority = Field(Enum(u'normal', u'high', name=u'message_priority'), default=u'normal')
    created = Field(DateTime, default=datetime.datetime.now)
    read = Field(DateTime)

    recipient = ManyToOne('User', inverse='messages')

    def __repr__(self):
        return ('<Message: "%s: %s", prio=%s>' % (self.recipient, self.subject, self.priority)).encode('utf-8')

    def __unicode__(self):
        return u'%s: %s' % (self.recipient, self.subject)


class Job(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    status = Field(Enum(u'pending', u'running', u'done', u'failed', u'abandoned', name=u'job_status'))
    task = Field(Enum(u'find', u'proc', u'find&proc', name=u'job_task'))
    needs_rerun = Field(Boolean, default=False)
    progress = Field(Integer)
    activity = Field(Unicode(255))

    data_container = ManyToOne('DataContainer', inverse='jobs')

    def __repr__(self):
        return ('<Job %d: %s, %s>' % (self.id, self.task, self.status)).encode('utf-8')

    def __unicode__(self):
        return u'%s %s' % (self.data_container, self.task)


class AccessPrivilege(object):

    privilege_names = {
        1: (u'Anon-Read'),
        2: (u'Read-Only'),
        3: (u'Read-Write'),
        4: (u'Manage'),
        }

    privilege_values = dict((i[1],i[0]) for i in privilege_names.iteritems())

    @classmethod
    def name(cls, priv):
        return cls.privilege_names[priv] if priv in cls.privilege_names else None

    @classmethod
    def names(cls):
        return cls.privilege_names.values()

    @classmethod
    def value(cls, priv):
        return cls.privilege_values[priv] if priv in cls.privilege_values else None

    @classmethod
    def values(cls):
        return cls.privilege_values.values()


class Access(Entity):

    user = ManyToOne('User')
    experiment = ManyToOne('Experiment')
    privilege = Field(Integer)

    def __init__(self, **kwargs):
        if 'privilege_name' in kwargs:
            kwargs['privilege'] = AccessPrivilege.value(kwargs['privilege_name'])
        super(Access, self).__init__(**kwargs)

    def __unicode__(self):
        return u'%s: (%s, %s)' % (AccessPrivilege.name(self.privilege), self.user, self.experiment)


class ResearchGroup(Entity):

    gid = Field(Unicode(32), unique=True)
    name = Field(Unicode(255))

    pis = ManyToMany('User', inverse='pi_groups')
    managers = ManyToMany('User', inverse='managers')
    members = ManyToMany('User', inverse='research_groups')

    experiments = OneToMany('Experiment')

    def __repr__(self):
        return (u'<%s: %s>' % (self.__class__.__name__, self.gid)).encode('utf-8')

    def __unicode__(self):
        return self.name or self.gid

    @classmethod
    def get_all_ids(cls):
        return [rg.gid for rg in cls.query.all()]


class Person(Entity):

    roles = OneToMany('Subject')

    @property
    def experiments(self):
        return [r.experiment for r in roles]


class DataContainer(Entity):

    using_options(inheritance='multi')

    timestamp = Field(DateTime, default=datetime.datetime.now)
    duration = Field(Interval, default=datetime.timedelta())
    trashtime = Field(DateTime)
    dirty = Field(Boolean, default=False, index=True)
    scheduling = Field(Boolean, default=False, index=True)

    datasets = OneToMany('Dataset')
    jobs = OneToMany('Job')

    def __repr__(self):
        return (u'<%s: %s>' % (self.__class__.__name__, self.name)).encode('utf-8')

    @property
    def primary_dataset(self):
        return Dataset.query.filter_by(container=self).filter_by(kind=u'primary').first()

    @property
    def original_datasets(self):
        return Dataset.query.filter(Dataset.container == self).filter((Dataset.kind == u'primary') | (Dataset.kind == u'secondary')).all()

    @property
    def is_trash(self):
        return bool(self.trashtime)


class Experiment(DataContainer):

    using_options(inheritance='multi')

    name = Field(Unicode(63), required=True)
    irb = Field(Unicode(16))

    owner = ManyToOne('ResearchGroup', required=True)
    accesses = OneToMany('Access')
    subjects = OneToMany('Subject')

    def __unicode__(self):
        return u'%s/%s' % (self.owner, self.name)

    @classmethod
    def from_owner_name(cls, owner, name):
        experiment = cls.query.filter_by(owner=owner).filter_by(name=name).first()
        if not experiment:
            experiment = cls(owner=owner, name=name)
            for manager in set(owner.managers + owner.pis):                         # managers & PIs
                Access(experiment=experiment, user=manager, privilege_name=u'Manage')
            for member in set(owner.members) - set(owner.managers + owner.pis):     # other members
                Access(experiment=experiment, user=member, privilege_name=u'Read-Only')
        return experiment

    @property
    def persons(self):
        return [s.person for s in self.subject]

    @property
    def next_subject_code(self):
        code_num = max([int('0%s' % re.sub(r'[^0-9]+', '', subj.code)) for subj in self.subjects]) + 1 if self.subjects else 1
        return u's%03d' % code_num

    @property
    def contains_trash(self):
        if self.is_trash:
            return True
        for subject in self.subjects:
            if subject.contains_trash:
                return True
        return False

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime
        for subject in self.subjects:
            subject.trash(trashtime)

    def untrash(self, propagate=True):
        self.trashtime = None
        if propagate:
            for subject in self.subjects:
                subject.untrash()

    def renumber_subjects(self):
        ordered_subjects = sorted(self.subjects, key=lambda subj: (sorted(subj.sessions, key=lambda session: session.timestamp)[0].timestamp))
        for i, subj in enumerate(ordered_subjects):
            subj.code = u's%03d' % (i+1)


class Subject(DataContainer):

    using_options(inheritance='multi')

    code = Field(Unicode(31))
    firstname = Field(Unicode(63))
    lastname = Field(Unicode(63))
    dob = Field(Date)
    #consent_form = Field(Unicode(63))

    experiment = ManyToOne('Experiment')
    person = ManyToOne('Person')
    sessions = OneToMany('Session')

    def __unicode__(self):
        return u'%s, %s' % (self.lastname, self.firstname)

    @classmethod
    def from_mrfile(cls, mrfile):
        group_name, exp_name = nimsutil.parse_patient_id(mrfile.patient_id, ResearchGroup.get_all_ids())
        query = cls.query.join(Experiment, cls.experiment).filter(Experiment.name==exp_name)
        if mrfile.subj_code:
            subject = query.filter(cls.code==mrfile.subj_code).first()
        elif mrfile.subj_fn and mrfile.subj_ln:
            subject = query.filter(cls.firstname==mrfile.subj_fn).filter(cls.lastname==mrfile.subj_ln).filter(cls.dob==mrfile.subj_dob).first()
        else:
            subject = None
        if not subject:
            owner = ResearchGroup.query.filter_by(gid=group_name).one()
            experiment = Experiment.from_owner_name(owner, exp_name)
            subj_code = mrfile.subj_code or experiment.next_subject_code
            subject = cls(
                    experiment=experiment,
                    person=Person(),
                    code=subj_code,
                    firstname=mrfile.subj_fn,
                    lastname=mrfile.subj_ln,
                    dob=mrfile.subj_dob,
                    )
        return subject

    @classmethod
    def for_session_in_experiment(cls, session, experiment):
        subject = cls.query.filter_by(person=session.subject.person).filter_by(experiment=experiment).first()
        if not subject:
            subject = session.subject.clone(experiment)
        return subject

    @property
    def name(self):
        return u'%s %s: %s, %s' % (self.code, self.sessions[0].timestamp, self.lastname, self.firstname)

    @property
    def contains_trash(self):
        if self.is_trash:
            return True
        for session in self.sessions:
            if session.contains_trash:
                return True
        return False

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime
        for session in self.sessions:
            session.trash(trashtime)

    def untrash(self, propagate=True):
        self.trashtime = None
        self.experiment.untrash(propagate=False)
        if propagate:
            for session in self.sessions:
                session.untrash()

    def clone(self, experiment):
        subj = Subject()
        for prop in self.mapper.iterate_properties:
            if prop.key != 'id' and prop.key != 'sessions':
                setattr(subj, prop.key, getattr(self, prop.key))
        subj.code = experiment.next_subject_code    # must be done before setting subj.experiment
        subj.experiment = experiment
        return subj


class Session(DataContainer):

    using_options(inheritance='multi')

    uid = Field(LargeBinary(32), index=True)
    exam = Field(Integer)
    notes = Field(Unicode)

    subject = ManyToOne('Subject')
    operator = ManyToOne('User')
    epochs = OneToMany('Epoch')

    def __unicode__(self):
        return u'Session'

    @classmethod
    def from_mrfile(cls, mrfile):
        uid = nimsutil.pack_dicom_uid(mrfile.exam_uid)
        session = cls.query.filter_by(uid=uid).first()
        if not session:
            subject = Subject.from_mrfile(mrfile)
            # If we trusted the scan operator to carefully enter their uid in the
            # 'operator' field, then we could make create=True. Or we could add some
            # fancy code to fuzzily infer their intent, perhaps even ldap-ing the uid
            # central authority and/or querying the schedule database. But for now,
            # just let the operator be None if the user isn't already in the system.
            operator = User.by_uid(unicode(mrfile.operator), create=False)
            session = Session(uid=uid, exam=mrfile.exam_no, subject=subject, operator=operator)
        return session

    @property
    def name(self):
        return u'%s_%d' % (self.timestamp.strftime(u'%Y%m%d_%H%M'), self.exam)

    @property
    def contains_trash(self):
        if self.is_trash:
            return True
        for epoch in self.epochs:
            if epoch.contains_trash:
                return True
        return False

    @property
    def experiment(self):
        return DBSession.query(Session, Experiment).join(Subject, Session.subject).join(Experiment, Subject.experiment).filter(Session.id == self.id).one().Experiment

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime
        for epoch in self.epochs:
            epoch.trash(trashtime)

    def untrash(self, propagate=True):
        self.trashtime = None
        self.subject.untrash(propagate=False)
        if propagate:
            for epoch in self.epochs:
                epoch.untrash()

    def move_to_experiment(self, experiment):
        old_subject = self.subject
        self.subject = Subject.for_session_in_experiment(self, experiment)
        if not old_subject.sessions:
            old_subject.delete()

class Epoch(DataContainer):

    using_options(inheritance='multi')

    uid = Field(LargeBinary(32), index=True)
    series = Field(Integer)
    acq = Field(Integer, index=True)
    description = Field(Unicode(255))
    psd = Field(Unicode(255))
    physio_recorded = Field(Boolean, default=False)
    physio_valid = Field(Boolean)

    tr = Field(Float)
    te = Field(Float)
    ti = Field(Float)
    flip_angle = Field(Float)
    pixel_bandwidth = Field(Float)
    num_slices = Field(Integer)
    num_timepoints = Field(Integer)
    num_averages = Field(Float)
    num_echos = Field(Integer)
    receive_coil_name = Field(Unicode(255))
    num_receivers = Field(Integer)
    protocol_name = Field(Unicode(255))
    scanner_name = Field(Unicode(255))
    size_x = Field(Integer)
    size_y = Field(Integer)
    fov = Field(Unicode(255))
    scan_type = Field(Unicode(255))
    num_bands = Field(Integer)
    prescribed_duration = Field(Interval, default=datetime.timedelta())
    mm_per_vox = Field(Unicode(255))
    effective_echo_spacing = Field(Float)
    phase_encode_undersample = Field(Float)
    slice_encode_undersample = Field(Float)
    acquisition_matrix = Field(Unicode(255))

    session = ManyToOne('Session')

    def __unicode__(self):
        return u'Epoch %s %s' % (self.session.subject.experiment, self.timestamp.strftime('%Y-%m-%d %H:%M:%S'))

    @classmethod
    def from_mrfile(cls, mrfile):
        uid = nimsutil.pack_dicom_uid(mrfile.series_uid)
        epoch = cls.query.filter_by(uid=uid).filter_by(acq=mrfile.acq_no).first()
        if not epoch:
            session = Session.from_mrfile(mrfile)
            if session.timestamp is None or session.timestamp > mrfile.timestamp:
                session.timestamp = mrfile.timestamp
            epoch = cls(
                    session = session,
                    timestamp = mrfile.timestamp,
                    duration = mrfile.duration,
                    prescribed_duration = mrfile.prescribed_duration,
                    uid = uid,
                    series = mrfile.series_no,
                    acq = mrfile.acq_no,
                    description = nimsutil.clean_string(mrfile.series_desc),
                    psd = unicode(mrfile.psd_name),
                    physio_recorded = mrfile.physio_flag,
                    tr = mrfile.tr,
                    te = mrfile.te,
                    ti = mrfile.ti,
                    flip_angle = mrfile.flip_angle,
                    pixel_bandwidth = mrfile.pixel_bandwidth,
                    num_slices = mrfile.num_slices,
                    num_timepoints = mrfile.num_timepoints,
                    num_averages = mrfile.num_averages,
                    num_echos = mrfile.num_echos,
                    receive_coil_name = unicode(mrfile.receive_coil_name),
                    num_receivers = mrfile.num_receivers,
                    protocol_name = unicode(mrfile.protocol_name),
                    scanner_name = unicode(mrfile.scanner_name),
                    size_x = mrfile.size_x,
                    size_y = mrfile.size_y,
                    fov = unicode(str(mrfile.fov)),
                    mm_per_vox = unicode(str(mrfile.mm_per_vox)),
                    scan_type = unicode(mrfile.scan_type),
                    num_bands = mrfile.num_bands,
                    effective_echo_spacing = mrfile.effective_echo_spacing,
                    phase_encode_undersample = mrfile.phase_encode_undersample,
                    slice_encode_undersample = mrfile.slice_encode_undersample,
                    acquisition_matrix = unicode(str(mrfile.acquisition_matrix)),
                    # to unpack fov, mm_per_vox, and acquisition_matrix: np.fromstring(str(mm)[1:-1],sep=',')
                    )
        return epoch

    @property
    def name(self):
        return '%s_%d_%d_%s' % (self.timestamp.strftime('%H%M%S'), self.series, self.acq, self.description)

    @property
    def contains_trash(self):
        if self.is_trash:
            return True
        for dataset in self.datasets:
            if dataset.is_trash:
                return True
        return False

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime
        for dataset in self.datasets:
            dataset.trash(trashtime)

    def untrash(self, propagate=True):
        self.trashtime = None
        self.session.untrash(propagate=False)
        if propagate:
            for dataset in self.datasets:
                dataset.untrash()


class Dataset(Entity):

    default_labels = {
            u'pfile':   u'GE PFile',
            u'dicom':   u'Dicom Data',
            u'nifti':   u'NIfTI',
            u'bitmap':  u'Bitmap',
            u'img_pyr': u'Image Pyramid',
            u'physio':  u'Physio Data',
            }

    label = Field(Unicode(63))  # informational only
    offset = Field(Interval, default=datetime.timedelta())
    trashtime = Field(DateTime)
    priority = Field(Integer, default=0)
    kind = Field(Enum(u'primary', u'secondary', u'peripheral', u'derived', name=u'dataset_kind'))
    filetype = Field(Enum(u'pfile', u'dicom', u'nifti', u'bitmap', u'img_pyr', u'physio', name=u'dataset_filetype'))
    datatype = Field(Enum(u'unknown', u'mr_fmri', u'mr_dwi', u'mr_structural', u'mr_fieldmap', u'mr_spectro', name=u'dataset_datatype'), default=u'unknown')
    _updatetime = Field(DateTime, default=datetime.datetime.now, colname='updatetime', synonym='updatetime')
    digest = Field(LargeBinary(20))
    compressed = Field(Boolean, default=False)
    archived = Field(Boolean, default=False, index=True)
    file_cnt_act = Field(Integer)
    file_cnt_tgt = Field(Integer)

    container = ManyToOne('DataContainer')
    parents = ManyToMany('Dataset')

    def __repr__(self):
        return (u'<%s: %s>' % (self.__class__.__name__, self.label)).encode('utf-8')

    def __unicode__(self):
        return u'<%s %s>' % (self.__class__.__name__, self.container)

    @classmethod
    def at_path(cls, nims_path, filetype, label=None, archived=False):
        dataset = cls(filetype=filetype, label=(label if label else cls.default_labels[filetype]), archived=archived)
        transaction.commit()
        DBSession.add(dataset)
        nimsutil.make_joined_path(nims_path, dataset.relpath)
        return dataset

    @classmethod
    def from_mrfile(cls, mrfile, nims_path, archived=True):
        series_uid = nimsutil.pack_dicom_uid(mrfile.series_uid)
        dataset = (cls.query.join(Epoch)
                .filter(Epoch.uid == series_uid)
                .filter(Epoch.acq == mrfile.acq_no)
                .filter(cls.filetype == mrfile.filetype)
                .first())
        if not dataset:
            alt_dataset = (cls.query.join(Epoch)
                    .filter(Epoch.uid == series_uid)
                    .filter(Epoch.acq == mrfile.acq_no)
                    .filter(cls.filetype != mrfile.filetype)
                    .first())
            if not alt_dataset:
                kind = u'primary'
            elif alt_dataset.priority < mrfile.priority:
                kind = u'primary'
                alt_dataset.kind = u'secondary'
            else:
                kind = u'secondary'
            epoch = Epoch.from_mrfile(mrfile)
            dataset = cls(
                    container=epoch,
                    priority = mrfile.priority,
                    filetype=mrfile.filetype,
                    kind=kind,
                    label=cls.default_labels[mrfile.filetype],
                    archived=archived,
                    )
            transaction.commit()
            DBSession.add(dataset)
            nimsutil.make_joined_path(nims_path, dataset.relpath)
        return dataset

    def shadowpath(self, user):
        db_query = (DBSession.query(Dataset, Epoch, Session, Experiment, ResearchGroup)
                .join(Epoch, Dataset.container)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment)
                .join(ResearchGroup, Experiment.owner)
                .filter(Dataset.id == self.id))
        db_result = db_query.first()
        return '/data/%s/%s/%s/%s/%s/%s' % (
                u'superuser' if user.is_superuser else user.uid,
                db_result.ResearchGroup.gid,
                db_result.Experiment.name,
                db_result.Session.name,
                db_result.Epoch.name,
                db_result.Dataset.name)

    @property
    def name(self):
        return nimsutil.clean_string(self.label)

    @property
    def relpath(self):
        return '%s/%03d/%08d' % ('archive' if self.archived else 'data', self.id % 1000, self.id)

    def _get_updatetime(self):
        return self._updatetime
    def _set_updatetime(self, updatetime):
        self._updatetime = updatetime
        self.container.dirty = True
    updatetime = property(_get_updatetime, _set_updatetime)

    @property
    def is_trash(self):
        return bool(self.trashtime)

    @property
    def contains_trash(self):
        return self.is_trash

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime

    def untrash(self, propagate=True):
        self.trashtime = None
        self.container.untrash(propagate=False)

    def redigest(self, nims_path):
        old_digest = self.digest
        new_hash = hashlib.sha1()
        filelist = os.listdir(os.path.join(nims_path, self.relpath))
        for filename in sorted(filelist):
            with open(os.path.join(nims_path, self.relpath, filename), 'rb') as fd:
                for chunk in iter(lambda: fd.read(1048576 * new_hash.block_size), ''):
                    new_hash.update(chunk)
        self.digest = new_hash.digest()
        self.file_cnt_act = len(filelist)
        return self.digest != old_digest

    def datatype_from_mrfile(self, mrfile):
        return u'unknown'
