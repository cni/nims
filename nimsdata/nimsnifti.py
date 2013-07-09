# @author:  Bob Dougherty
#           Gunnar Schaefer

import nimsdata


class NIMSNiftiError(nimsdata.NIMSDataError):
    pass


class NIMSNifti(nimsdata.NIMSData):

    """
    A NIfTI file wrapped in a NIMS-sortable object.

    TODO: consider moving the nifti-header loading and file-writing from the NIMSImage subclasses to here.
    Then, e.g., NIMSDicom will pass the relevant metadata and the image array to NIMSNifti to write the file.
    """

    # TODO: add metadata necessary for sorting to the NIfTI header.
    def __init__(self):
        super(NIMSNifti, self).__init__()
        raise NIMSNiftiError('NIMSNifti class not yet implemented')
