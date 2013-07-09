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
        self.session_spec = { '_id': self.exam_uid}
        self.db_acq_key = '%s_%s' % (self.series_no, self.acq_no)
        self._db_info = None
        self._experiment_info = None
        self._session_info = None
        self._epoch_info = None

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
                    'firstname':        self.subj_fn,
                    'lastname':         self.subj_ln,
                    'dob':              self.subj_dob,
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
