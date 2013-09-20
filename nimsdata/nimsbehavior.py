# @author:  Gunnar Schaefer
#           Bob Dougherty

import nimsdata


class NIMSBehaviorError(nimsdata.NIMSDataError):
    pass


class NIMSBehavior(nimsdata.NIMSData):

    def __init__(self, filepath):
        raise NIMSBehaviorError('NIMSBehavior class not yet implemented')
        super(NIMSBehavior, self).__init__()
