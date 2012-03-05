import os
import gzip
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

__all__  = ['Group', 'User', 'Permission', 'Message', 'Job']
__all__ += ['Access', 'AccessPrivilege', 'ResearchGroup', 'Subject', 'SubjectRole']
__all__ += ['Experiment', 'Session', 'Epoch', 'Dataset']
__all__ += ['FreeDataset', 'Screensave' , 'RawNifti', 'PreprocNifti', 'MRIPhysioData']
__all__ += ['MRIDataset', 'DicomData', 'Pfile']


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
            query = query.join(Experiment, Session.experiment)
            query = query.join(Access, Experiment.accesses)
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
    task = Field(Unicode(63), required=True)
    max_workers = Field(Integer, default=1)
    status = Field(Enum(u'new', u'active', u'done', u'failed', name=u'status'), default=u'new')

    dataset = ManyToOne('Dataset', inverse='jobs')

    def __unicode__(self):
        return u'<Job %s: %s>' % (self.task, self.dataset)


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


class Subject(Entity):

    firstname = Field(Unicode(63))
    lastname = Field(Unicode(63))
    dob = Field(Date)

    roles = OneToMany('SubjectRole')

    def __unicode__(self):
        return u'%s, %s' % (self.lastname, self.firstname)

    @classmethod
    def by_firstname_lastname_dob(cls, firstname, lastname, dob):
        subject = cls.query.filter_by(firstname=firstname).filter_by(lastname=lastname).filter_by(dob=dob).first()
        if not subject:
            subject = cls(firstname=firstname, lastname=lastname, dob=dob)
        return subject

    @property
    def experiments(self):
        return Experiment.query.join(Session).join(SubjectRole).filter(SubjectRole.subject==self).all()


class SubjectRole(Entity):

    subject = ManyToOne('Subject')
    sessions = OneToMany('Session')

    def __unicode__(self):
        return u'%s: %s' % (self.experiment, self.subject)

    @classmethod
    def by_subject_experiment(cls, subject, experiment):
        role = cls.query.join(Session).filter(cls.subject==subject).filter(Session.experiment==experiment).first()
        if not role:
            role = cls(subject=subject)
        return role

    @property
    def experiment(self):
        return self.sessions[0].experiment


class Experiment(Entity):

    trashtime = Field(DateTime)
    name = Field(Unicode(63))
    irb = Field(Unicode(16))

    owner = ManyToOne('ResearchGroup', required=True)
    accesses = OneToMany('Access')
    sessions = OneToMany('Session')

    def __unicode__(self):
        return u'%s: %s' % (self.owner, self.name)

    @classmethod
    def by_owner_name(cls, owner, name):
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
    def subject_roles(self):
        return SubjectRole.query.join(Session).filter(Session.experiment==self).all()

    @property
    def subjects(self):
        return Subject.query.join(SubjectRole).join(Session).filter(Session.experiment==self).all()

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
        self.trashtime = None


class Session(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    trashtime = Field(DateTime)
    mri_exam = Field(Integer)
    notes = Field(Unicode)

    experiment = ManyToOne('Experiment')
    subject_role = ManyToOne('SubjectRole')
    operator = ManyToOne('User')
    epochs = OneToMany('Epoch')

    @classmethod
    def from_metadata(cls, md):
        session = cls.query.filter_by(mri_exam=md.mri_exam).first()
        if not session:
            owner = ResearchGroup.query.filter_by(gid=md.group_name).one()
            experiment = Experiment.by_owner_name(owner, md.exp_name)
            subject = Subject.by_firstname_lastname_dob(md.subj_fn, md.subj_ln, md.subj_dob)
            subject_role = SubjectRole.by_subject_experiment(subject, experiment)
            session = Session(mri_exam=md.mri_exam, subject_role=subject_role, experiment=experiment)
        return session

    @property
    def name(self):
        return '%s_%d' % (self.timestamp.strftime('%Y%m%d'), self.mri_exam)

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
            self.experiment.untrash()


class Epoch(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    trashtime = Field(DateTime)
    physio_flag = Field(Boolean, default=False)
    has_physio = Field(Boolean, default=False)

    mri_series = Field(Integer)
    mri_acq = Field(Integer)
    mri_desc = Field(Unicode(255))

    session = ManyToOne('Session')
    datasets = OneToMany('Dataset')
    free_datasets = ManyToMany('FreeDataset')

    def __unicode__(self):
        return u'<Epoch %5d %04d %02d %s>' % (self.session.mri_exam, self.mri_series, self.mri_acq, self.mri_desc)

    @classmethod
    def from_metadata(cls, md):
        query = cls.query.join(Session, cls.session)
        query = query.filter(Session.mri_exam==md.mri_exam)
        query = query.filter(cls.mri_series==md.mri_series)
        query = query.filter(cls.mri_acq==md.mri_acq)
        epoch = query.first()
        if not epoch:
            session = Session.from_metadata(md)
            if session.timestamp is None or session.timestamp > md.timestamp:
                session.timestamp = md.timestamp
            epoch = cls(session=session, timestamp=md.timestamp, mri_series=md.mri_series, mri_acq=md.mri_acq, mri_desc=md.mri_desc)
        return epoch

    @property
    def name(self):
        return ('%04d_%02d_%s' % (self.mri_series, self.mri_acq, self.mri_desc)).encode('utf-8')

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


class Dataset(Entity):

    tasks = []
    label = ''

    trashtime = Field(DateTime)
    offset_secs = Field(Float)
    duration_secs = Field(Float)
    name = Field(Unicode(31))
    updated_at = Field(DateTime, default=datetime.datetime.now)
    file_cnt_act = Field(Integer, default=0)
    file_cnt_tgt = Field(Integer, default=0)
    is_dirty = Field(Boolean, default=False)
    path_prefix = Field(Unicode(31))

    epoch = ManyToOne('Epoch')
    jobs = OneToMany('Job')

    def __unicode__(self):
        return u'<%s %s>' % (self.__class__.__name__, self.epoch)

    @property
    def path(self):
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
            self.epoch.untrash()


class FreeDataset(Dataset):

    epochs = ManyToMany('Epoch')


class Screensave(Dataset):

    pass


class MRIPhysioData(Dataset):

    tasks = [u'preproc']


class RawNifti(Dataset):

    @property
    def tasks(self):
        return [u'find_physio'] if self.epoch.physio_flag else [u'preproc']


class PreprocNifti(Dataset):

    pass


class MRIDataset(Dataset):

    priority = 0
    filename_ext = ''

    psd_name = Field(Unicode(255))
    #is_spiral = Field(Boolean)

    @classmethod
    def from_file(cls, fp):
        metadata = cls.get_metadata(fp)
        return cls.from_metadata(metadata) if metadata else None

    @classmethod
    def from_metadata(cls, md):
        query = cls.query.join(Epoch, cls.epoch).join(Session, Epoch.session)
        query = query.filter(Session.mri_exam==md.mri_exam)
        query = query.filter(Epoch.mri_series==md.mri_series)
        query = query.filter(Epoch.mri_acq==md.mri_acq)
        dataset = query.first()
        if not dataset:
            epoch = Epoch.from_metadata(md)
            epoch.physio_flag = md.physio_flag and u'epi' in md.psd_name.lower()
            dataset = cls(epoch=epoch, psd_name=md.psd_name)
            transaction.commit()
            DBSession.add(dataset)
        return dataset


class DicomData(MRIDataset):

    priority = 0
    label = '.dicoms'
    filename_ext = '.dcm'
    tasks = [u'dcm_to_nii']

    @staticmethod
    def get_metadata(fp):

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
            header = dicom.read_file(fp, stop_before_pixels=True)
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
            md.subj_fn, md.subj_ln, md.subj_dob = nimsutil.parse_subject(header.PatientsName, header.PatientsBirthDate)
            md.group_name, md.exp_name = nimsutil.parse_patient_id(header.PatientID, ResearchGroup.get_all_ids())
        return md


class Pfile(MRIDataset):

    priority = 1
    label = 'pfiles'
    tasks = [u'pfile_to_nii']

    @staticmethod
    def get_metadata(fp):
        try:
            from nimsutil import pfheader
        except ImportError:
            print '==========  PFHEADER NOT FOUND  =========='
            return None

        try:
            header = pfheader.get_header(fp)
        except (IOError, pfheader.PfreaderError):
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
            md.subj_fn, md.subj_ln, md.subj_dob = nimsutil.parse_subject(header.exam.patnameff, header.exam.dateofbirth)
            md.group_name, md.exp_name = nimsutil.parse_patient_id(header.exam.patidff, ResearchGroup.get_all_ids())
        return md


class Metadata(object):

    def __init__(self):
        pass
