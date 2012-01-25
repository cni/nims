import os
import re
import glob
import gzip
import zipfile
import datetime
import subprocess as sp

import dicom
from elixir import *

import nimsutil

from nimsgears.model import metadata, DBSession
from nimsgears.model import AccessPrivilege, Access, ResearchGroup

__session__ = DBSession
__metadata__ = metadata

__all__  = ['Job', 'Subject', 'Experiment', 'Session', 'Epoch', 'Dataset', 'FreeDataset']
__all__ += ['Screensave' , 'RawNifti', 'PreprocNifti', 'MRIPhysioData']
__all__ += ['MRIDataset', 'DicomData', 'Pfile']

RE_DATETIME_STR = re.compile('.+(?P<datetime>\d{10}_\d{2}_\d{2}_\d{1,3})')
DAY_TIMEDELTA = datetime.timedelta(days=1)


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


class Experiment(Entity):

    name = Field(Unicode(63))
    irb = Field(Unicode(16))

    owner = ManyToOne('ResearchGroup', required=True)
    accesses = OneToMany('Access')
    sessions = OneToMany('Session')

    def __unicode__(self):
        return self.name


class Session(Entity):

    mri_exam = Field(Integer)
    notes = Field(Unicode)

    experiment = ManyToOne('Experiment')
    subject = ManyToOne('Subject')
    operator = ManyToOne('User')
    epochs = OneToMany('Epoch')

    @property
    def timestamp(self):
      return min([e.timestamp for e in Epoch.query.filter_by(session=self)])

    @property
    def name(self):
        return '%s_%d' % (self.timestamp.strftime('%Y%m%d'), self.mri_exam)


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

    @property
    def name(self):
        return '%04d_%02d_%s' % (self.mri_series, self.mri_acq, self.mri_desc)

    @property
    def path(self):
        return os.path.join(self.session.experiment.owner.id, self.session.name)


#class DataType(Entity):
#
#    name = Field(Unicode(31))
#
#    datasets = OneToMany('Dataset')


class Dataset(Entity):

    tasks = []
    label = ''

    offset_secs = Field(Float)
    duration_secs = Field(Float)

    name = Field(Unicode(31))
    #is_collection = Field(Boolean)
    updated_at = Field(DateTime, default=datetime.datetime.now)
    is_dirty = Field(Boolean, default=False)

    epoch = ManyToOne('Epoch')
    jobs = OneToMany('Job')
    #data_type = ManyToOne('DataType')

    @property
    def path(self):
        return os.path.join(self.epoch.path, self.epoch.name+self.label)


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

    @classmethod
    def from_file(cls, fp):
        """Return epoch object for provided file."""
        return cls.from_header(cls.get_header(fp))


class DicomData(MRIDataset):

    priority = 0
    label = '.dicoms'
    filename_ext = '.dcm'
    tasks = [u'dcm_to_nii']

    @classmethod
    def from_header(cls, header):
        """Return dataset object for provided header."""
        if not header:
            return None

        exam_num = int(header.StudyID)
        series_num = int(header.SeriesNumber)
        acq_num = int(header.AcquisitionNumber) if 'AcquisitionNumber' in header else 0

        query = cls.query.join('epoch', 'session')
        query = query.filter(Session.mri_exam==exam_num).filter(Epoch.mri_series==series_num).filter(Epoch.mri_acq==acq_num)
        dataset = query.first()

        if not dataset:
            query = Epoch.query.join('session')
            query = query.filter(Session.mri_exam==exam_num).filter(Epoch.mri_series==series_num).filter(Epoch.mri_acq==acq_num)
            epoch = query.first()

            if not epoch:
                session = Session.query.filter_by(mri_exam=exam_num).first()

                if not session:
                    all_subjects = [(subj.lastname, subj.firstname, subj.dob) for subj in Subject.query.all()]
                    subj_ln, subj_fn, subj_dob = nimsutil.parse_subject(header.PatientsName, header.PatientsBirthDate, all_subjects)
                    all_groups = [rg.id for rg in ResearchGroup.query.all()]
                    group_name, exp_name = nimsutil.parse_patient_id(header.PatientID, all_groups)
                    subject = Subject.query.filter_by(lastname=subj_ln).filter_by(firstname=subj_fn).filter_by(dob=subj_dob).first()
                    owner = ResearchGroup.query.filter_by(id=group_name).first()
                    experiment = Experiment.query.filter_by(owner=owner).filter_by(name=exp_name).first()

                    if not subject:
                        subject = Subject(lastname=subj_ln, firstname=subj_fn)

                    if not experiment:
                        experiment = Experiment(owner=owner, name=exp_name)
                        adm_priv = AccessPrivilege.query.filter_by(name=u'mg').one()
                        mem_priv = AccessPrivilege.query.filter_by(name=u'ro').one()
                        for admin in set(owner.admins + owner.pis):                         # admins & PIs
                            Access(experiment=experiment, user=admin, privilege=adm_priv)
                        for member in set(owner.members) - set(owner.admins + owner.pis):   # other members
                            Access(experiment=experiment, user=member, privilege=mem_priv)

                    session = Session(mri_exam=exam_num, subject=subject, experiment=experiment)

                ts = datetime.datetime.strptime(nimsutil.acq_date(header)+nimsutil.acq_time(header), '%Y%m%d%H%M%S')
                series_desc = nimsutil.clean_string(header.SeriesDescription)
                epoch = Epoch(session=session, timestamp=ts, mri_series=series_num, mri_acq=acq_num, mri_desc=series_desc)

            psd_name = nimsutil.psd_name(header)
            epoch.physio_flag = nimsutil.physio_flag and u'epi' in psd_name.lower()
            dataset = cls(epoch=epoch, psd_name=psd_name)

        return dataset

    @staticmethod
    def get_header(fp):
        try:
            header = dicom.read_file(fp, stop_before_pixels=True)
            if header.Manufacturer != 'GE MEDICAL SYSTEMS':
                header = None
        except (IOError, dicom.filereader.InvalidDicomError):
            header = None
        return header

    #def process(self, dest):
    #    exam_path = os.path.join(dest, self.exam_path)
    #    dicom_path = os.path.join(exam_path, self.label, self.series_dir)
    #    filename_list = [os.path.join(dicom_path, basename) for basename in os.listdir(dicom_path)]
    #    header_list = [dicom.read_file(filename) for filename in filename_list]
    #    nimsutil.process_data(header_list, os.path.join(exam_path, self.series_dir))


class Pfile(MRIDataset):

    priority = 1
    label = 'pfiles'
    is_spiral = Field(Boolean)

    @classmethod
    def from_header(cls, header):
        """Return epoch object for provided header."""
        if not header:
            return None

        # FIXME:
        all_groups = []

        exam_num = header.exam.ex_no
        series_num = header.series.se_no
        acquisition_num = header.image.scanactno
        epoch = cls.query.with_lockmode('update').filter_by(exam_num=exam_num, series_num=series_num, acquisition_num=acquisition_num).first()
        if not epoch:
            lab_id, experiment_id = nimsutil.parse_patient_id(header.exam.patidff, all_groups)
            series_desc = nimsutil.clean_string(header.series.se_desc)
            month, day, year = map(int, header.rec.scan_date.split('/'))
            hour, minute = map(int, header.rec.scan_time.split(':'))
            timestamp = datetime.datetime(year + 1900, month, day, hour, minute) # GE's epoch begins in 1900
            psd_name = os.path.basename(header.image.psdname)
            is_spiral = 'sprt' in psd_name.lower()
            physio_flag = header.rec.user2 and is_spiral
            epoch = cls(exam_num=exam_num, series_num=series_num, acquisition_num=acquisition_num, lab_id=lab_id, experiment_id=experiment_id, series_desc=series_desc, timestamp=timestamp, psd_name=psd_name, is_spiral=bool(is_spiral), physio_flag=bool(physio_flag))
        return epoch

    @staticmethod
    def get_header(fp):
        from nimsutil import pfreader
        try:
            header = pfreader.get_header(fp)
        except (IOError, pfreader.PfreaderError):
            header = None
        return header

    def process(self, dest):
        exam_path = os.path.join(dest, self.exam_path)
        pfile_path = os.path.join(exam_path, self.label, self.series_dir)
        filename = [os.path.join(pfile_path, basename) for basename in os.listdir(pfile_path)].pop()
        with nimsutil.TempDirectory() as temp_dir:
            temp_filename = os.path.join(temp_dir, os.path.basename(filename))
            os.symlink(filename, temp_filename)
            if self.is_spiral:
                self._recon(temp_filename, exam_path)

    def _recon(self, filename, store_to):
        sp.call(['fmspiralmag.m', filename], stdout=open('/dev/null', 'w'), stderr=sp.STDOUT)
        # if nifti exists post-recon, gzip it into the epoch folder
        nii_filename = filename + '.nii'
        if os.path.isfile(nii_filename):
            gzip_nii_filename = os.path.join(store_to, self.series_dir + '.nii.gz')
            with open(nii_filename, 'rb') as nii_file, gzip.open(gzip_nii_filename, 'wb') as gzip_nii_file:
                gzip_nii_file.writelines(nii_file)
