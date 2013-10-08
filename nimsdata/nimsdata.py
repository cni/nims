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
    file_fields = [
            ('datakind', 'datakind'),
            ('datatype', 'datatype'),
            ('filetype', 'filetype'),
            ]

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
        else:
            raise NIMSDataError('%s could not be parsed' % filepath)
        return dataset

    @abc.abstractmethod
    def __init__(self):
        pass

    @property
    def canonical_filename(self):
        return '%s_%s_%s_%s' % (self.exam_uid.replace('.', '_'), self.series_no, self.acq_no, self.filetype)

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
        return filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in self.session_fields]) + kwargs.items()

    def get_epoch_info(self, **kwargs):
        return filter(lambda t: t[1] is not None, [(field, getattr(self, field_name, None)) for field, field_name in self.epoch_fields]) + kwargs.items()

    def get_file_info(self, **kwargs):
        return filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in self.file_fields]) + kwargs.items()

    def get_file_spec(self, _prefix, **kwargs):
        file_spec = filter(lambda t: t[1], [(field, getattr(self, field_name, None)) for field, field_name in NIMSData.file_fields])
        return [(_prefix + key, value) for key, value in file_spec + kwargs.items()]
