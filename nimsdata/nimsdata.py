# @author:  Gunnar Schaefer
#           Bob Dougherty

import abc
import datetime


class NIMSDataError(Exception):
    pass


class NIMSData(object):

    __metaclass__ = abc.ABCMeta

    parse_priority = 0

    session_fields = [
            ('exam', 'exam_no'),
            ('patient_id', 'patient_id'),
            ('firstname', 'subj_firstname'),
            ('lastname', 'subj_lastname'),
            ('dob', 'subj_dob'),
            ('sex', 'subj_sex'),
            ]
    epoch_fields = [
            ('timestamp', 'timestamp'),
            ('series', 'series_no'),
            ('acquisition', 'acq_no'),
            ('description', 'series_desc'),
            ]
    dataset_fields = [
            ('datakind', 'datakind'),
            ('datatype', 'datatype'),
            ('filetype', 'filetype'),
            ]
    file_fields = []

    @classmethod
    def parse(cls, filepath):
        def __all_subclasses(cls):
            subclasses = []
            for sc in cls.__subclasses__():
                subclasses += [sc] + __all_subclasses(sc)
            return subclasses
        subclasses = sorted(
                filter(lambda cls: not bool(getattr(cls, '__abstractmethods__')), __all_subclasses(cls)),
                key=lambda sc: sc.parse_priority,
                reverse=True
                )
        for sc in subclasses:
            try:
                dataset = sc(filepath)
            except NIMSDataError:
                dataset = None
            else:
                break
        return dataset

    @abc.abstractmethod
    def __init__(self):
        self.session_spec = {'_id': self.exam_uid}
        self.epoch_key = '%s_%s' % (self.series_no, self.acq_no)
        self.dataset_key = '%s_%s_%s' % (self.datakind, self.datatype, self.filetype)
        self._deep_session_info = None
        self._metadata = None
        self._session_info = None
        self._epoch_info = None
        self._dataset_info = None
        self._file_info = None

    @property
    def canonical_filename(self):
        return '%s_%s_%s_%s' % (self.exam_uid.replace('.', '_'), self.series_no, self.acq_no, self.filetype)

    @property
    def deep_session_info(self):
        if self._deep_session_info is None:
            self._deep_session_info = self.get_session_info(
                    epochs={self.epoch_key: dict(self.get_epoch_info(
                        datasets={self.dataset_key: dict(self.get_dataset_info())}
                        ))},
                    **self.session_spec
                    )
        return dict(self._deep_session_info)

    def get_metadata(self, tgt_cls=None):
        tgt_cls = tgt_cls or self.__class__
        field_names = [('_id', 'exam_uid')] + tgt_cls.session_fields + tgt_cls.epoch_fields
        return {t[0]: t[1] for t in [(field_name, getattr(self, field_name, None)) for field, field_name in field_names] if t[1]}

    def set_metadata_fields(self, metadata_fields):
        for field_name, value in metadata_fields.iteritems():
            if isinstance(value, datetime.datetime):
                value = value.replace(tzinfo=None)
            setattr(self, field_name, value)

    def get_session_info(self, **kwargs):
        if self._session_info is None:
            self._session_info = filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in self.session_fields])
        return self._session_info + kwargs.items()

    def get_epoch_info(self, **kwargs):
        if self._epoch_info is None:
            self._epoch_info = filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in self.epoch_fields])
        return self._epoch_info + kwargs.items()

    def get_dataset_info(self, **kwargs):
        if self._dataset_info is None:
            self._dataset_info = filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in self.dataset_fields])
        return self._dataset_info + kwargs.items()

    def get_file_info(self, **kwargs):
        if self._file_info is None:
            self._file_info = filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in self.file_fields])
        return self._file_info + kwargs.items()
