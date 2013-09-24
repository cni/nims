# @author:  Gunnar Schaefer
#           Reno Bowen
#           Bob Dougherty

import os
import re
import shutil
import hashlib
import datetime

import transaction
from elixir import *

import nimsutil
from nimsgears.model import metadata, DBSession

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
    uid_number = Field(Integer, index=True)
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
        return Group.by_gid(u'superusers') in self.groups and self.admin_mode

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
        return 0 #len([msg for msg in self.messages if not msg.read]) if self.messages else 0

    @property
    def dataset_cnt(self):
        query = DBSession.query(Session)
        if not self.is_superuser:
            query = query.join(Subject, Session.subject).join(Experiment, Subject.experiment).join(Access).filter(Access.user==self)
        return query.count()

    @property
    def job_cnt(self):
        return Job.query.filter((Job.status == u'pending') | (Job.status == u'running')).count()

    def _get_trash_flag(self):
        return session.get('trash_flag', 0)
    def _set_trash_flag(self, trash_flag):
        session['trash_flag'] = trash_flag
        session.save()
    trash_flag = property(_get_trash_flag, _set_trash_flag)

    @property
    def admin_groups(self):
        return ResearchGroup.query.all() if self.is_superuser else self.pi_groups + self.manager_groups

    @property
    def admin_group_names(self):
        return sorted([group.gid for group in self.admin_groups])

    @property
    def member_groups(self):
        return ResearchGroup.query.all() if self.is_superuser else self.pi_groups + self.manager_groups + self.research_groups

    @property
    def member_group_names(self):
        return sorted([group.gid for group in self.member_groups])

    def manages_group(self, group):
        return group in self.admin_groups

    def is_group_pi(self, group):
        return self.is_superuser or self in group.pis

    def _filter_access(self, query, min_access_level=u'Anon-Read'):
        return query.join(Access).filter(Access.user == self).filter(Access.privilege >= AccessPrivilege.value(min_access_level))

    def has_access_to(self, data_container, min_access_level=u'Anon-Read'):
        if self.is_superuser:
            return True
        else:
            data_container.toplevel_query().first()
            return bool(self._filter_access(data_container.toplevel_query(), min_access_level)
                    .filter(data_container.__class__.id == data_container.id)
                    .first())

    def experiments_with_access_privilege(self, min_access_level=u'Anon-Read', ignore_superuser=False):
        query = Experiment.toplevel_query()
        if not self.is_superuser or ignore_superuser:
            query = self._filter_access(query, min_access_level)
        if self.trash_flag == 0:
            query = query.filter(Experiment.trashtime == None)
        elif self.trash_flag == 2:
            query = query.filter(Experiment.trashtime != None)
        if self.is_superuser and not ignore_superuser:
            return [(exp, u'Manage') for exp in query.all()]
        else:
            return [(exp, AccessPrivilege.name(acc.privilege)) for exp, acc in query.add_entity(Access).all()]

    def experiments(self, min_access_level=u'Anon-Read', ignore_superuser=False):
        return [exp for exp, acc in self.experiments_with_access_privilege(min_access_level, ignore_superuser)]

    def sessions(self, exp_id, min_access_level=u'Anon-Read'):
        query = Session.toplevel_query().filter(Experiment.id == exp_id)
        if not self.is_superuser:
            query = self._filter_access(query, min_access_level)
        if self.trash_flag == 0:
            query = query.filter(Session.trashtime == None)
        elif self.trash_flag == 2:
            query = query.filter(Session.trashtime != None)
        return query.all()

    def epochs(self, sess_id, min_access_level=u'Anon-Read'):
        query = Epoch.query.join(Session, Epoch.session).filter(Session.id == sess_id).join(Subject, Session.subject).join(Experiment, Subject.experiment) ## FIXME: use toplevel_query (sqlalchemy is broken, filter and join have order dependency)
        if not self.is_superuser:
            query = self._filter_access(query, min_access_level)
        if self.trash_flag == 0:
            query = query.filter(Epoch.trashtime == None)
        elif self.trash_flag == 2:
            query = query.filter(Epoch.trashtime != None)
        return query.all()

    def datasets(self, epoch_id, min_access_level=u'Anon-Read'):
        query = Dataset.query.join(Epoch, Dataset.container).filter(Epoch.id == epoch_id).join(Session, Epoch.session).join(Subject, Session.subject).join(Experiment, Subject.experiment) ## FIXME: use toplevel_query (sqlalchemy is broken, filter and join have order dependency)
        if not self.is_superuser:
            query = self._filter_access(query, min_access_level)
        if self.trash_flag == 0:
            query = query.filter(Dataset.trashtime == None)
        elif self.trash_flag == 2:
            query = query.filter(Dataset.trashtime != None)
        return query.all()

    def latest_exp_session(self, min_access_level=u'Anon-Read'):
        query = DBSession.query(Experiment, Session).join(Subject, Experiment.subjects).join(Session, Subject.sessions)
        if not self.is_superuser:
            query = self._filter_access(query, min_access_level)
        if self.trash_flag == 0:
            query = query.filter(Session.trashtime == None)
        elif self.trash_flag == 2:
            query = query.filter(Session.trashtime != None)
        return query.order_by(Session.timestamp.desc()).first() or (None, None)


class Permission(Entity):

    """Permission definition for :mod:`repoze.what`; `permission_name` required."""

    pid = Field(Unicode(32), unique=True)           # translation for permission_name set in app_cfg.py
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

    def __repr__(self):
        return (u'%s' % self).encode('utf-8')

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
    def all_ids(cls):
        return [rg.gid for rg in cls.query.all()]

    @property
    def all_member_ids(self):
        return [u.uid for u in (self.pis + self.managers + self.members)]


class Person(Entity):

    roles = OneToMany('Subject')

    @property
    def experiments(self):
        return [r.experiment for r in self.roles]


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
        return (u'<%s: %s>' % (self.__class__.__name__, self)).encode('utf-8')

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

    @classmethod
    def toplevel_query(self):
        return Experiment.query

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

    def users_with_access_privilege(self, user):
        user_access = User.query.join(Access).add_entity(Access).filter(Access.experiment == self).filter(Access.user == user).first()
        if user.is_superuser or user_access.Access.privilege == AccessPrivilege.value(u'Manage'):
            db_results = User.query.join(Access).add_entity(Access).filter(Access.experiment == self).all()
        else:
            db_results = [user_access]
        return [(user, AccessPrivilege.name(acc.privilege)) for user, acc in db_results]

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
        subj_code, group_name, exp_name = nimsutil.parse_patient_id(mrfile.patient_id, ResearchGroup.all_ids())
        query = cls.query.join(Experiment, cls.experiment).filter(Experiment.name == exp_name)
        query = query.join(ResearchGroup, Experiment.owner).filter(ResearchGroup.gid == group_name)
        if subj_code:
            subject = query.filter(cls.code==subj_code).first()
        elif mrfile.subj_firstname and mrfile.subj_lastname:
            subject = query.filter(cls.firstname==mrfile.subj_firstname).filter(cls.lastname==mrfile.subj_lastname).filter(cls.dob==mrfile.subj_dob).first()
        else:
            subject = None
        if not subject:
            owner = ResearchGroup.query.filter_by(gid=group_name).one()
            experiment = Experiment.from_owner_name(owner, exp_name)
            subject = cls(
                    experiment=experiment,
                    person=Person(),
                    code=subj_code[:31] or experiment.next_subject_code,
                    firstname=mrfile.subj_firstname[:63],
                    lastname=mrfile.subj_lastname[:63],
                    dob=mrfile.subj_dob,
                    )
        return subject

    @classmethod
    def for_session_in_experiment(cls, session, experiment):
        subject = cls.query.filter_by(person=session.subject.person).filter_by(experiment=experiment).first()
        if not subject:
            subject = session.subject.clone(experiment)
        return subject

    @classmethod
    def toplevel_query(self):
        return (Subject.query
                .join(Experiment, Subject.experiment))

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
        return self.name

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

    @classmethod
    def toplevel_query(self):
        return (Session.query
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))

    @property
    def name(self):
        return u'%s_%d' % (self.timestamp.strftime('%Y%m%d_%H%M'), self.exam)

    @property
    def dirname(self):
        return u'%s' % self.timestamp.strftime('%Y%m%d_%H%M')

    @property
    def legacy_dirname(self):
        return u'%s_%s' % (self.timestamp.strftime('%Y%m%d'), self.exam)

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
    notes = Field(Unicode)
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
                    duration = datetime.timedelta(0, mrfile.duration),
                    prescribed_duration = datetime.timedelta(0, mrfile.prescribed_duration),
                    uid = uid,
                    series = mrfile.series_no,
                    acq = mrfile.acq_no,
                    description = nimsutil.clean_string(mrfile.series_desc),
                    psd = unicode(mrfile.psd_name),
                    physio_recorded = True,
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
                    size_x = mrfile.size[0],
                    size_y = mrfile.size[1],
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

    @classmethod
    def toplevel_query(cls):
        return (Epoch.query
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))

    @property
    def name(self):
        return '%d_%d_%d' % (self.session.exam, self.series, self.acq)

    @property
    def dirname(self):
        return '%d_%d_%s' % (self.series, self.acq, self.description)

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
            u'img_pyr': u'Image Viewer',
            u'physio':  u'Physio Data',
            }

    label = Field(Unicode(63))  # informational only
    offset = Field(Interval, default=datetime.timedelta())
    trashtime = Field(DateTime)
    priority = Field(Integer, default=0)
    kind = Field(Enum(u'primary', u'secondary', u'peripheral', u'derived', u'web', name=u'dataset_kind'))
    filetype = Field(Enum(u'pfile', u'dicom', u'nifti', u'bitmap', u'img_pyr', u'physio', name=u'dataset_filetype'))
    datatype = Field(Enum(u'unknown', u'mr_fmri', u'mr_dwi', u'mr_structural', u'mr_fieldmap', u'mr_spectro', name=u'dataset_datatype'), default=u'unknown')
    _updatetime = Field(DateTime, default=datetime.datetime.now, colname='updatetime', synonym='updatetime')
    digest = Field(LargeBinary(20))
    compressed = Field(Boolean, default=False)
    archived = Field(Boolean, default=False, index=True)
    _filenames = Field(String, default='', colname='filenames', synonym='filenames')

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
                    .filter(cls.kind == u'primary')
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
                    compressed=mrfile.compressed,
                    kind=kind,
                    label=cls.default_labels[mrfile.filetype],
                    archived=archived,
                    )
            transaction.commit()
            DBSession.add(dataset)
            nimsutil.make_joined_path(nims_path, dataset.relpath)
        return dataset

    @classmethod
    def toplevel_query(cls):
        return (Dataset.query
                .join(Epoch, Dataset.container)
                .join(Session, Epoch.session)
                .join(Subject, Session.subject)
                .join(Experiment, Subject.experiment))

    @property
    def name(self):
        return nimsutil.clean_string(self.label)

    @property
    def relpath(self):
        return '%s/%03d/%08d' % ('archive' if self.archived else 'current', self.id % 1000, self.id)

    def _get_updatetime(self):
        return self._updatetime
    def _set_updatetime(self, updatetime):
        self._updatetime = updatetime
        self.container.dirty = True
    updatetime = property(_get_updatetime, _set_updatetime)

    def _get_filenames(self):
        return self._filenames.split(', ') if self._filenames else []
    def _set_filenames(self, filenames):
        self._filenames = ', '.join(filenames)
    filenames = property(_get_filenames, _set_filenames)

    @property
    def primary_file_relpath(self):
        fn = self._get_filenames()
        if len(fn)<=1:
            primary_file = fn[0] if len(fn)==1 else []
        else:
            if self.filetype==u'pfile':
                primary_file = next((f for f in fn if f.startswith('P') and f.endswith('.7.gz') and len(f)==11), [])
            elif self.filetype==u'dicom':
                primary_file = next((f for f in fn if f.endswith('_dicoms.tgz')), [])
            elif self.filetype==u'nifti':
                primary_file = next((f for f in fn if f.endswith('.nii.gz')), [])
            elif self.filetype==u'bitmap':
                primary_file = next((f for f in fn if f.endswith('.png')), [])
            elif self.filetype==u'img_pyr':
                primary_file = next((f for f in fn if f.endswith('.pyrdb')), [])
            elif self.filetype==u'physio':
                primary_file = next((f for f in fn if f.endswith('.physio.tgz')), [])
            else:
                primary_file = fn[0]
        return os.path.join(self.relpath, primary_file)

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

    def datatype_from_mrfile(self, mrfile):
        return u'unknown'
