# @author:  Gunnar Schaefer
#           Bob Dougherty

import abc
import datetime

import nimsdata

SLICE_ORDER_UNKNOWN = 0
SLICE_ORDER_SEQ_INC = 1
SLICE_ORDER_SEQ_DEC = 2
SLICE_ORDER_ALT_INC = 3
SLICE_ORDER_ALT_DEC = 4


class NIMSImageError(nimsdata.NIMSDataError):
    pass


# TODO: pull up common meta-data fields and methods from the subclasses.
class NIMSImage(nimsdata.NIMSData):

    __metaclass__ = abc.ABCMeta

    datakind = u'raw'
    datatype = u'mri'

    @abc.abstractmethod
    def __init__(self):
        super(NIMSImage, self).__init__()

    def parse_subject_name(self, name):
        lastname, firstname = name.split('^') if '^' in name else ('', '')
        return firstname.title(), lastname.title()

    def parse_subject_dob(self, dob):
        try:
            dob = datetime.datetime.strptime(dob, '%Y%m%d')
            if dob < datetime.datetime(1900, 1, 1):
                raise ValueError
        except ValueError:
            dob = None
        return dob
