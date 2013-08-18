# @author:  Gunnar Schaefer
#           Bob Dougherty

import nimsdata


class NIMSBehaviorError(nimsdata.NIMSDataError):
    pass


class NIMSBehavior(nimsdata.NIMSData):

    def __init__(self):
        super(NIMSBehavior, self).__init__()
        raise NIMSBehaviorError('NIMSBehavior class not yet implemented')
