import os
import re
import random
import hashlib
import datetime

import dicom
import transaction
from elixir import *

import nimsutil
from nimsgears.model import metadata, DBSession

__session__ = DBSession
__metadata__ = metadata

__all__  = ['Group', 'User', 'Permission', 'Message', 'Job', 'Access', 'AccessPrivilege']
__all__ += ['ResearchGroup', 'Person', 'Subject', 'DataContainer', 'Experiment', 'Session', 'Epoch']
__all__ += ['Dataset', 'MRData', 'DicomData' , 'GEPfile', 'NiftiData']


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
    name = Field(Unicode(255))
    email = Field(Unicode(255), info={'rum': {'field':'Email'}})
    _password = Field(Unicode(128), colname='password', info={'rum': {'field':'Password'}}, synonym='password')
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
            ldap_name, ldap_email = nimsutil.ldap_query(kwargs['uid'])
            kwargs['name'] = ldap_name or kwargs['uid']
            kwargs['email'] = ldap_email
        super(User, self).__init__(**kwargs)

    def __repr__(self):
        return ('<User: %s, %s, "%s">' % (self.uid, self.email, self.name)).encode('utf-8')

    def __unicode__(self):
        return self.name or self.uid

    @classmethod
    def by_email(cls, email):
        return cls.query.filter_by(email=email).first()

    @classmethod
    def by_uid(cls, uid, create=False, password=None):
        user = cls.query.filter_by(uid=uid).first()
        if not user and create:
            user = cls(uid=uid, password=password)
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
        if not self in Group.by_gid(u'superusers').users or not self.admin_mode:
            query = query.join(Subject, Session.subject).join(Experiment, Subject.experiment).join(Access)
            query = query.filter(Access.user==self)
        return query.count()


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
    priority = Field(Enum(u'normal', u'high', name=u'priority'), default=u'normal')
    created = Field(DateTime, default=datetime.datetime.now)
    read = Field(DateTime)

    recipient = ManyToOne('User', inverse='messages')

    def __repr__(self):
        return ('<Message: "%s: %s", prio=%s>' % (self.recipient, self.subject, self.priority)).encode('utf-8')

    def __unicode__(self):
        return u'%s: %s' % (self.recipient, self.subject)


class Job(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    status = Field(Enum(u'new', u'active', u'done', u'failed', name=u'status'), default=u'new')
    task = Field(Enum(u'find', u'proc', name=u'task'))
    redo_all = Field(Boolean, default=False)
    progress = Field(Integer)
    action = Field(Unicode(255))

    data_container = ManyToOne('DataContainer', inverse='jobs')

    def __unicode__(self):
        return u'Job %d (%s): %s' % (self.id if self.id else -1, self.task, self.data_container)


class Access(Entity):

    user = ManyToOne('User')
    experiment = ManyToOne('Experiment')
    privilege = ManyToOne('AccessPrivilege')

    def __unicode__(self):
        return u'%s: (%s, %s)' % (self.privilege, self.user, self.experiment)


class AccessPrivilege(Entity):

    value = Field(Integer, required=True)
    name = Field(Unicode(32), required=True)
    description = Field(Unicode(255))

    access = OneToMany('Access')

    def __unicode__(self):
        return self.description or self.name


class ResearchGroup(Entity):

    gid = Field(Unicode(32), unique=True)
    name = Field(Unicode(255))

    pis = ManyToMany('User', inverse='pi_groups')
    managers = ManyToMany('User', inverse='managers')
    members = ManyToMany('User', inverse='research_groups')

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
    trashtime = Field(DateTime)
    needs_finding = Field(Boolean, default=False)
    needs_processing = Field(Boolean, default=False)

    datasets = OneToMany('Dataset')
    jobs = OneToMany('Job')

    @property
    def primary_dataset(self):
        return Dataset.query.filter_by(container=self).filter_by(kind=u'primary').first()


class Experiment(DataContainer):

    using_options(inheritance='multi')

    name = Field(Unicode(63))
    irb = Field(Unicode(16))

    owner = ManyToOne('ResearchGroup', required=True)
    accesses = OneToMany('Access')
    subjects = OneToMany('Subject')

    def __unicode__(self):
        return u'%s: %s' % (self.owner, self.name)

    @classmethod
    def from_owner_name(cls, owner, name):
        experiment = cls.query.filter_by(owner=owner).filter_by(name=name).first()
        if not experiment:
            experiment = cls(owner=owner, name=name)
            mng_priv = AccessPrivilege.query.filter_by(name=u'mg').one()
            mem_priv = AccessPrivilege.query.filter_by(name=u'ro').one()
            for manager in set(owner.managers + owner.pis):                         # managers & PIs
                Access(experiment=experiment, user=manager, privilege=mng_priv)
            for member in set(owner.members) - set(owner.managers + owner.pis):     # other members
                Access(experiment=experiment, user=member, privilege=mem_priv)
        return experiment

    @property
    def persons(self):
        return [s.person for s in self.subject]

    @property
    def is_trash(self):
        return bool(self.trashtime)

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

    def untrash(self):
        if self.is_trash:
            self.trashtime = None
            for subject in self.subjects:
                subject.untrash()


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
    def from_metadata(cls, md):
        query = cls.query.join(Experiment, cls.experiment).filter(Experiment.name==md.exp_name)
        if md.subj_code:
            query = query.filter(cls.code==md.subj_code)
        else:
            query = query.filter(cls.firstname==md.subj_fn).filter(cls.lastname==md.subj_ln).filter(cls.dob==md.subj_dob)
        subject = query.first()
        if not subject:
            owner = ResearchGroup.query.filter_by(gid=md.group_name).one()
            experiment = Experiment.from_owner_name(owner, md.exp_name)
            if md.subj_code is None:
                code_num = max([int('0%s' % re.sub(r'[^0-9]+', '', s.code)) for s in experiment.subjects]) + 1 if experiment.subjects else 1
                md.subj_code = u's%03d' % code_num
            subject = cls(experiment=experiment, person=Person(), code=md.subj_code, firstname=md.subj_fn, lastname=md.subj_ln, dob=md.subj_dob)
        return subject

    @property
    def is_trash(self):
        return bool(self.trashtime)

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

    def untrash(self):
        if self.is_trash:
            self.trashtime = None
            self.experiment.untrash()
            for session in self.sessions:
                session.untrash()


class Session(DataContainer):

    using_options(inheritance='multi')

    notes = Field(Unicode)

    subject = ManyToOne('Subject')
    operator = ManyToOne('User')
    epochs = OneToMany('Epoch')

    def __unicode__(self):
        return u'Session'

    @classmethod
    def from_metadata(cls, md):
        session = cls.query.join(Epoch, Session.epochs).join(Dataset).filter(Dataset.exam==md.mri_exam).first()
        if not session:
            subject = Subject.from_metadata(md)
            operator = None # FIXME: set operator to an actual user, creating user if necessary
            session = Session(subject=subject, operator=operator)
        return session

    @property
    def name(self):
        return '%s_%d' % (self.timestamp.strftime('%Y%m%d'), self.mri_exam)

    @property
    def mri_exam(self):
        dataset = MRData.query.join(Epoch, MRData.container).filter(Epoch.session==self).first()
        return dataset.exam if dataset else None

    @property
    def is_trash(self):
        return bool(self.trashtime)

    @property
    def contains_trash(self):
        if self.is_trash:
            return True
        for epoch in self.epochs:
            if epoch.contains_trash:
                return True
        return False

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime
        for epoch in self.epochs:
            epoch.trash(trashtime)

    def untrash(self):
        if self.is_trash:
            self.trashtime = None
            self.subject.untrash()
            for epoch in self.epochs:
                epoch.untrash()


class Epoch(DataContainer):

    using_options(inheritance='multi')

    session = ManyToOne('Session')

    def __unicode__(self):
        return u'Epoch %5d %04d %02d %s' % (self.session.mri_exam, self.mri_series, self.mri_acq, self.mri_desc)

    @classmethod
    def from_metadata(cls, md):
        query = cls.query.join(Dataset)
        query = query.filter(Dataset.exam==md.mri_exam).filter(Dataset.series==md.mri_series).filter(Dataset.acq==md.mri_acq)
        epoch = query.first()
        if not epoch:
            session = Session.from_metadata(md)
            if session.timestamp is None or session.timestamp > md.timestamp:
                session.timestamp = md.timestamp
            epoch = cls(session=session, timestamp=md.timestamp)
        return epoch

    @property
    def name(self):
        return ('%04d_%02d_%s' % (self.mri_series, self.mri_acq, self.mri_desc)).encode('utf-8')

    @property
    def original_dataset(self):
        return self.datasets[0].source

    @property
    def mri_series(self):
        dataset = MRData.query.filter(MRData.container==self).first()
        return dataset.series if dataset else None

    @property
    def mri_acq(self):
        dataset = MRData.query.filter(MRData.container==self).first()
        return dataset.acq if dataset else None

    @property
    def mri_desc(self):
        dataset = MRData.query.filter(MRData.container==self).first()
        return dataset.desc if dataset else None

    @property
    def is_trash(self):
        return bool(self.trashtime)

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

    def untrash(self):
        if self.is_trash:
            self.trashtime = None
            self.session.untrash()
            for dataset in self.datasets:
                dataset.untrash()


class Dataset(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    trashtime = Field(DateTime)
    kind = Field(Enum(u'primary', u'secondary', u'derived', name=u'kind'), default=u'primary')
    type = Field(Enum(u'dicom', u'pfile', u'nifti', u'physio', u'screensave', name=u'type'))
    updated_at = Field(DateTime, default=datetime.datetime.now)
    path_prefix = Field(Unicode(31))

    offset = Field(Float)
    duration = Field(Float)
    file_cnt_act = Field(Integer, default=0)
    file_cnt_tgt = Field(Integer, default=0)

    container = ManyToOne('DataContainer')
    parents = ManyToMany('Dataset')

    def __unicode__(self):
        return u'<%s %s>' % (self.__class__.__name__, self.container)

    @classmethod
    def at_path_for_file_and_type(cls, nims_path, filename=None, type=None):
        dataset = cls(type=type)
        transaction.commit()
        DBSession.add(dataset)
        os.makedirs(os.path.join(nims_path, dataset.relpath))
        return dataset

    @property
    def relpath(self):
        if self.path_prefix is None:
            self.path_prefix = u'%03d' % random.randint(0,999)
        return os.path.join(self.path_prefix, '%08d' % self.id).encode('utf-8')

    @property
    def is_trash(self):
        return bool(self.trashtime)

    @property
    def contains_trash(self):
        return self.is_trash

    def trash(self, trashtime=datetime.datetime.now()):
        self.trashtime = trashtime

    def untrash(self):
        if self.is_trash:
            self.trashtime = None
            self.container.untrash()


class MRData(Dataset):

    """Abstract superclass to all MRI data types."""

    priority = 0
    filename_ext = ''

    exam = Field(Integer)
    series = Field(Integer)
    acq = Field(Integer)
    desc = Field(Unicode(255))
    psd = Field(Unicode(255))
    physio_flag = Field(Boolean, default=False)
    has_physio = Field(Boolean, default=False)

    tr = Field(Float)
    te = Field(Float)

    @classmethod
    def at_path_for_file_and_type(cls, nims_path, filename, type=None):
        metadata = cls.get_metadata(filename)
        if metadata:
            dataset = cls.from_metadata(metadata)
            transaction.commit()
            DBSession.add(dataset)
            os.makedirs(os.path.join(nims_path, dataset.relpath))
        else:
            dataset = None
        return dataset

    @classmethod
    def from_metadata(cls, md):
        dataset = cls.query.filter_by(exam=md.mri_exam).filter_by(series=md.mri_series).filter_by(acq=md.mri_acq).first()
        if not dataset:
            epoch = Epoch.from_metadata(md)
            epoch.needs_finding = True
            epoch.needs_processing = True
            dataset = cls(container=epoch, exam=md.mri_exam, series=md.mri_series, acq=md.mri_acq, desc=md.mri_desc, psd=md.psd_name)
            dataset.timestamp = md.timestamp
            dataset.physio_flag = md.physio_flag and u'epi' in md.psd_name.lower()
        return dataset


class DicomData(MRData):

    priority = 0
    filename_ext = '.dcm'

    @staticmethod
    def get_metadata(filename):

        TAG_PSD_NAME =    (0x0019, 0x109c)
        TAG_PHYSIO_FLAG = (0x0019, 0x10ac)

        def acq_date(header):
            if 'AcquisitionDate' in header: return header.AcquisitionDate
            elif 'StudyDate' in header:     return header.StudyDate
            else:                           return '19000101'

        def acq_time(header):
            if 'AcquisitionTime' in header: return header.AcquisitionTime
            elif 'StudyTime' in header:     return header.StudyTime
            else:                           return '000000'

        try:
            header = dicom.read_file(filename, stop_before_pixels=True)
            if header.Manufacturer != 'GE MEDICAL SYSTEMS':    # TODO: make code more general
                raise dicom.filereader.InvalidDicomError
        except (IOError, dicom.filereader.InvalidDicomError):
            md = None
        else:
            md = Metadata()
            md.mri_exam = int(header.StudyID)
            md.mri_series = int(header.SeriesNumber)
            md.mri_acq = int(header.AcquisitionNumber) if 'AcquisitionNumber' in header else 0
            md.psd_name = unicode(os.path.basename(header[TAG_PSD_NAME].value)) if TAG_PSD_NAME in header else u''
            md.physio_flag = bool(header[TAG_PHYSIO_FLAG].value) if TAG_PHYSIO_FLAG in header else False
            md.mri_desc = nimsutil.clean_string(header.SeriesDescription)
            md.timestamp = datetime.datetime.strptime(acq_date(header) + acq_time(header), '%Y%m%d%H%M%S')
            md.subj_code, md.subj_fn, md.subj_ln, md.subj_dob = nimsutil.parse_subject(header.PatientsName, header.PatientsBirthDate)
            md.group_name, md.exp_name = nimsutil.parse_patient_id(header.PatientID, ResearchGroup.get_all_ids())
        return md


class GEPfile(MRData):

    priority = 1

    @staticmethod
    def get_metadata(filename):
        try:
            from nimsutil import pfheader
        except ImportError:
            print '==========  PFHEADER NOT FOUND  =========='
            return None

        try:
            header = pfheader.get_header(filename)
        except (IOError, pfheader.PfheaderError):
            md = None
        else:
            md = Metadata()
            md.mri_exam = header.exam.ex_no
            md.mri_series = header.series.se_no
            md.mri_acq = header.image.scanactno

            md.psd_name = unicode(os.path.basename(header.image.psdname))
            md.physio_flag = bool(header.rec.user2) and u'sprt' in md.psd_name.lower()
            md.mri_desc = nimsutil.clean_string(header.series.se_desc)
            month, day, year = map(int, header.rec.scan_date.split('/'))
            hour, minute = map(int, header.rec.scan_time.split(':'))
            md.timestamp = datetime.datetime(year + 1900, month, day, hour, minute) # GE's epoch begins in 1900
            all_groups = [rg.id for rg in ResearchGroup.query.all()]
            md.subj_code, md.subj_fn, md.subj_ln, md.subj_dob = nimsutil.parse_subject(header.exam.patnameff, header.exam.dateofbirth)
            md.group_name, md.exp_name = nimsutil.parse_patient_id(header.exam.patidff, ResearchGroup.get_all_ids())
        return md


class NiftiData(Dataset):

    pass


class Metadata(object):

        pass
