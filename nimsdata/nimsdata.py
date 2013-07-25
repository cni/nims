# @author:  Gunnar Schaefer
#           Bob Dougherty

import abc


class NIMSDataError(Exception):
    pass


class NIMSData(object):

    __metaclass__ = abc.ABCMeta

    @classmethod
    def parse(cls, filepath):
        try:
            dataset = cls(filepath)
        except (TypeError, NIMSDataError):
            for subclass in cls.__subclasses__():
                dataset = subclass.parse(filepath)
                if dataset: break
            else:
                dataset = None
        return dataset

    @abc.abstractmethod
    def __init__(self):
        self.unique_id = '%s_%s_%s' % (self.datakind, self.datatype, self.filetype)
        self.session_spec = { '_id': self.exam_uid}
        self.db_acq_key = '%s_%s' % (self.series_no, self.acq_no)
        self._db_info = None
        self._experiment_info = None
        self._session_info = None
        self._epoch_info = None
        self._dataset_info = None

    @property
    def db_info(self):
        if not self._db_info:
            self._db_info = self.session_info
            self._db_info['epochs'] = {
                    self.db_acq_key:    self.epoch_info
                    }
        return self._db_info

    @property
    def experiment_info(self):
        if not self._experiment_info:
            self._experiment_info = {
                    'owner':            self.owner,
                    'name':             self.exp_name,
                    }
        return self._experiment_info

    @property
    def session_info(self):
        if not self._session_info:
            self._session_info = {
                    'timestamp':        self.timestamp,
                    '_id':              self.exam_uid,
                    'exam':             self.exam_no,
                    'patient_id':       self.patient_id,
                    'firstname':        self.subj_firstname,
                    'lastname':         self.subj_lastname,
                    'dob':              self.subj_dob,
                    'sex':              self.subj_sex,
                    'epochs':           {},
                    }
        return self._session_info

    def get_session_info(self, **kwargs):
        return dict(self.session_info.items() + kwargs.items())

    @property
    def epoch_info(self):
        if not self._epoch_info:
            self._epoch_info = {
                    'timestamp':        self.timestamp,
                    'series':           self.series_no,
                    'acquisition':      self.acq_no,
                    'description':      self.series_desc,
                    'datasets':         {},
                    }
        return self._epoch_info

    def get_epoch_info(self, **kwargs):
        return dict(self.epoch_info.items() + kwargs.items())

    @property
    def dataset_info(self):
        if not self._dataset_info:
            self._dataset_info = {
                    'datakind': self.datakind,
                    'datatype': self.datatype,
                    'filetype': self.filetype,
                    }
        return self._dataset_info

    def get_dataset_info(self, **kwargs):
        return dict(self.dataset_info.items() + kwargs.items())
