import os
import gzip
import random
import datetime

import dicom
import transaction
from elixir import *

import nimsutil

from nimsgears.model import metadata, DBSession
from nimsgears.model import AccessPrivilege, Access, ResearchGroup

__session__ = DBSession
__metadata__ = metadata

__all__  = ['Job', 'Subject', 'Experiment', 'Session', 'Epoch', 'Dataset', 'FreeDataset']
__all__ += ['Screensave' , 'RawNifti', 'PreprocNifti', 'MRIPhysioData']
__all__ += ['MRIDataset', 'DicomData', 'Pfile']


class Metadata(object):

    def __init__(self):
        pass


class Job(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    task = Field(Unicode(63), required=True)
    max_workers = Field(Integer, default=1)
    status = Field(Enum(u'new', u'active', u'done', u'failed', name=u'status'), default=u'new')

    dataset = ManyToOne('Dataset', inverse='jobs')

    def __unicode__(self):
        return u'<Job %s: %s>' % (self.task, self.dataset)


class Subject(Entity):

    """
    we thought about a subject id column that defaults to 's' + db_id
    """

    firstname = Field(Unicode(63))
    lastname = Field(Unicode(63))
    dob = Field(DateTime)

    sessions = OneToMany('Session')

    def __unicode__(self):
        return u'%s, %s' % (self.lastname, self.firstname)

    @classmethod
    def by_firstname_lastname_dob(cls, firstname, lastname, dob):
        subject = cls.query.filter_by(firstname=firstname).filter_by(lastname=lastname).filter_by(dob=dob).first()
        if not subject:
            subject = cls(firstname=firstname, lastname=lastname, dob=dob)
        return subject


class Experiment(Entity):

    name = Field(Unicode(63))
    irb = Field(Unicode(16))

    owner = ManyToOne('ResearchGroup', required=True)
    accesses = OneToMany('Access')
    sessions = OneToMany('Session')

    def __unicode__(self):
        return self.name

    @classmethod
    def by_owner_name(cls, owner, name):
        experiment = cls.query.filter_by(owner=owner).filter_by(name=name).first()
        if not experiment:
            experiment = cls(owner=owner, name=name)
            adm_priv = AccessPrivilege.query.filter_by(name=u'mg').one()
            mem_priv = AccessPrivilege.query.filter_by(name=u'ro').one()
            for admin in set(owner.admins + owner.pis):                         # admins & PIs
                Access(experiment=experiment, user=admin, privilege=adm_priv)
            for member in set(owner.members) - set(owner.admins + owner.pis):   # other members
                Access(experiment=experiment, user=member, privilege=mem_priv)
        return experiment


class Session(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
    mri_exam = Field(Integer)
    notes = Field(Unicode)

    experiment = ManyToOne('Experiment')
    subject = ManyToOne('Subject')
    operator = ManyToOne('User')
    epochs = OneToMany('Epoch')

    @property
    def name(self):
        return '%s_%d' % (self.timestamp.strftime('%Y%m%d'), self.mri_exam)

    @property
    def path(self):
        return '%08d' % self.id

    @classmethod
    def from_metadata(cls, md):
        session = cls.query.filter_by(mri_exam=md.mri_exam).first()
        if not session:
            subject = Subject.by_firstname_lastname_dob(md.subj_fn, md.subj_ln, md.subj_dob)
            owner = ResearchGroup.query.filter_by(id=md.group_name).one()
            experiment = Experiment.by_owner_name(owner, md.exp_name)
            session = Session(mri_exam=md.mri_exam, subject=subject, experiment=experiment)
        return session


class Epoch(Entity):

    timestamp = Field(DateTime, default=datetime.datetime.now)
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

    @property
    def name(self):
        return ('%04d_%02d_%s' % (self.mri_series, self.mri_acq, self.mri_desc)).encode('utf-8')

    @property
    def path(self):
        return os.path.join(self.session.path) # FIXME: probably need more here

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


class Dataset(Entity):

    tasks = []
    label = ''

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
            md.physio_flag = header[TAG_PHYSIO_FLAG].value
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
            from nimsutil import pfreader
        except ImportError:
            print '==========  PFREADER NOT FOUND  =========='
            return None

        try:
            header = pfreader.get_header(fp)
        except (IOError, pfreader.PfreaderError):
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
