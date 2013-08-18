# @author:  Gunnar Schaefer
#           Bob Dougherty

import abc
import datetime
import logging

import numpy as np

import nimsdata

log = logging.getLogger('nimsimage')

SLICE_ORDER_UNKNOWN = 0
SLICE_ORDER_SEQ_INC = 1
SLICE_ORDER_SEQ_DEC = 2
SLICE_ORDER_ALT_INC = 3
SLICE_ORDER_ALT_DEC = 4

def compute_rotation(row_cos, col_cos, slice_norm):
    rot = np.zeros((3,3))
    rot = np.matrix(((-row_cos[0], -col_cos[0], -slice_norm[0]),
                     (-row_cos[1], -col_cos[1], -slice_norm[1]),
                     (row_cos[2], col_cos[2], slice_norm[2])), dtype=float)
    return rot

def build_affine(rotation, scale, origin):
    aff = np.zeros((4,4))
    aff[0:3,0:3] = rotation
    aff[:,3] = np.append(origin, 1).T
    aff[0:3,0:3] = np.dot(aff[0:3,0:3], np.diag(scale))
    return aff

def adjust_bvecs(bvecs, bvals, vendor, rotation=None):
    bvecs,bvals = scale_bvals(bvecs, bvals)
    if vendor.lower().startswith('ge') and rotation != None:
       log.debug('rotating bvecs with image orientation matrix')
       bvecs,bvals = rotate_bvecs(bvecs, bvals, rotation)
    else:
       bvecs,bvals = rotate_bvecs(bvecs, bvals, np.diag((-1.,-1.,1.)))
    return bvecs,bvals

def scale_bvals(bvecs, bvals):
    """
    Scale the b-values in bvals given non-unit-length bvecs. E.g., if the magnitude a
    bvec is 0.5, the corresponding bvalue will be scaled by 0.5^2. The bvecs are also
    scaled to be unit-length. Returns the adjusted bvecs and bvals.
    """
    sqmag = np.array([bv.dot(bv) for bv in bvecs.T])
    # The bvecs are generally stored with 3 decimal values. So, we get significant fluctuations in the
    # sqmag due to rounding error. To avoid spurious adjustments to the bvals, we round the sqmag based
    # on the number of decimal values.
    # TODO: is there a more elegant way to determine the number of decimals used?
    num_decimals = np.nonzero([np.max(np.abs(bvecs-bvecs.round(decimals=d))) for d in range(9)])[0][-1] + 1
    sqmag = np.around(sqmag, decimals=num_decimals-1)
    bvals *= sqmag           # Scale each bval by the squared magnitude of the corresponding bvec
    sqmag[sqmag==0] = np.inf # Avoid divide-by-zero
    bvecs /= np.sqrt(sqmag)  # Normalize each bvec to unit length
    return bvecs,bvals

def rotate_bvecs(bvecs, bvals, rotation):
    """
    Rotate diffusion gradient directions (bvecs) based on the 3x3 rotation matrix.
    Returns the adjusted bvecs and bvals.
    """
    bvecs = np.array(np.matrix(rotation) * bvecs)
    # Normalize each bvec to unit length
    norm = np.sqrt(np.array([bv.dot(bv) for bv in bvecs.T]))
    norm[norm==0] = np.inf # Avoid divide-by-zero
    bvecs /= norm
    return bvecs,bvals

def infer_psd_type(psd_name):
    if psd_name == 'sprt':
        psd_type = 'spiral'
    elif psd_name == 'sprl_hos':
        psd_type = 'hoshim'
    elif psd_name == 'basic':
        psd_type = 'basic'
    elif 'mux' in psd_name.lower(): # multi-band EPI!
        psd_type = 'mux'
    elif psd_name == 'Probe-MEGA':
        psd_type = 'mrs'
    else:
        psd_type = 'unknown'
    return psd_type



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

    def infer_scan_type(self):
        if self.psd_type == 'mrs':
            scan_type = 'spectroscopy'
        elif self.psd_type == 'hoshim':
            scan_type = 'shim'
        elif self.is_dwi:
            scan_type = 'diffusion'
        elif self.psd_type == 'spiral' and self.num_timepoints == 2 and self.te < .05:
            scan_type = 'fieldmap'
        elif self.te>0.02 and self.te<0.05 and self.num_timepoints>10 and 'epi' in self.psd_name.lower():
            scan_type = 'functional'
        elif ('fgre' in self.psd_name or 'ssfse' in self.psd_name) and self.fov[0]>=250. and self.fov[1]>=250. and self.mm_per_vox[2]>=5.:
            # Could be either a low-res calibration scan (e.g., ASSET cal) or a localizer.
            if self.mm_per_vox[0] > 2:
                scan_type = 'calibration'
            else:
                scan_type = 'localizer'
        else:
            # anything else will be an anatomical
            if self.acquisition_type.lower() == '3d':
                scan_type = '3D anatomy'
            elif self.acquisition_type.lower() == '2d':
                scan_type = '2D anatomy'
            else:
                scan_type = 'anatomy'
        return scan_type

