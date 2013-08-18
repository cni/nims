# @author:  Gunnar Schaefer

import os
import Image
import logging
import numpy as np

import nimsdata

log = logging.getLogger('nimspng')


class NIMSPNGError(nimsdata.NIMSDataError):
    pass


class NIMSPNG(nimsdata.NIMSData):

    datakind = u'derived'
    datatype = u'bitmap'
    filetype = u'png'

    def __init__(self):
        # TODO: add metadata to PNG header
        raise NIMSPNGError('NIMSPNG class not yet implemented')
        super(NIMSPNG, self).__init__()

    @staticmethod
    def write(metadata, imagedata, outbase):
        """Create png files for each image in a list of pixel data."""
        # TODO: add metadata to PNG header
        filepath = outbase + '.png'
        if imagedata.ndim == 2:
            imagedata = imagedata.astype(np.int32)
            imagedata = imagedata.clip(0, (imagedata * (imagedata != (2**15 - 1))).max())   # -32768->0; 32767->brain.max
            imagedata = imagedata * (2**8 -1) / imagedata.max()                             # scale to full 8-bit range
            Image.fromarray(imagedata.astype(np.uint8), 'L').save(filepath, optimize=True)
        elif imagedata.ndim == 3:
            imagedata = imagedata.reshape((imagedata.shape[1], imagedata.shape[2], imagedata.shape[0]))
            Image.fromarray(imagedata, 'RGB').save(filepath, optimize=True)
        log.debug('generated %s' % os.path.basename(filepath))
