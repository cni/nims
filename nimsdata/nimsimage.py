# @author:  Gunnar Schaefer
#           Bob Dougherty

import abc
import datetime

import nimsdata


class NIMSImageError(nimsdata.NIMSDataError):
    pass


# TODO: pull up common meta-data fields and methods from the subclasses.
class NIMSImage(nimsdata.NIMSData):

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self):
        super(NIMSImage, self).__init__()

    def parse_subject(self, name, dob):
        lastname, firstname = name.split('^') if '^' in name else ('', '')
        try:
            dob = datetime.datetime.strptime(dob, '%Y%m%d')
            if dob < datetime.datetime(1900, 1, 1):
                raise ValueError
        except ValueError:
            dob = None
        return (firstname.capitalize(), lastname.capitalize(), dob)
