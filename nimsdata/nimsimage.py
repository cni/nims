# @author:  Gunnar Schaefer
#           Bob Dougherty

import abc
import datetime
import logging

import numpy as np

import nimsdata

scan_types = [
        'spectroscopy',
        'perfusion',
        'shim',
        'diffusion',
        'fieldmap',
        'functional',
        'calibration',
        'localizer',
        'anatomy_t1w',
        'anatomy_t2w',
        'anatomy',
        ]
scan_types = type('Enum', (object,), dict(zip(scan_types, scan_types), all=scan_types))

log = logging.getLogger('nimsimage')

# NIFTI1-stype slice order codes:
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

def compute_slice_norm(self, row_cosines, col_cosines, pos_first, pos_last, imagedata=None):
    """
    Computes the slice normal from the x/y cosines and the position of the first and last slice.
    Returns the slice normal vector and a flag indicating if it was flipped.
    """
    # Compute the slice_norm. From the NIFTI-1 header:
    #     The third column of R will be either the cross-product of the first 2 columns or
    #     its negative. It is possible to infer the sign of the 3rd column by examining
    #     the coordinates in DICOM attribute (0020,0032) "Image Position (Patient)" for
    #     successive slices. However, this method occasionally fails for reasons that I
    #     (RW Cox) do not understand.
    # For Siemens data, it seems that looking at 'SliceNormalVector' can help resolve this.
    #    dicom_slice_norm = getelem(self._hdr, 'SliceNormalVector', float, None)
    #    if dicom_slice_norm != None and np.dot(self.slice_norm, dicom_slice_norm) < 0.:
    #        self.slice_norm = -self.slice_norm
    slice_norm = np.cross(row_cosines, col_cosines)
    if np.dot(slice_norm, pos_first) > np.dot(slice_norm, pos_last):
        slice_norm = -slice_norm
        flipped = True
    else:
        flipped = False
    return slice_norm,flipped

def build_affine(rotation, scale, origin):
    aff = np.zeros((4,4))
    aff[0:3,0:3] = rotation
    aff[:,3] = np.append(origin, 1).T
    aff[0:3,0:3] = np.dot(aff[0:3,0:3], np.diag(scale))
    return aff

def adjust_bvecs(bvecs, bvals, vendor, rotation=None):
    bvecs,bvals = scale_bvals(bvecs, bvals)
    # TODO: Uncomment the following when we are ready to fix the bvec flip issue:
    #if vendor.lower().startswith('ge') and rotation != None:
    #   log.debug('rotating bvecs with image orientation matrix')
    #   bvecs,bvals = rotate_bvecs(bvecs, bvals, rotation)
    #else:
    #   bvecs,bvals = rotate_bvecs(bvecs, bvals, np.diag((-1.,-1.,1.)))
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
    psd_name = psd_name.lower()
    if 'service' in psd_name:
        psd_type = 'service'
    elif psd_name == 'sprt':
        psd_type = 'spiral'
    elif psd_name == 'sprl_hos':
        psd_type = 'hoshim'
    elif psd_name == 'basic':
        psd_type = 'basic'
    elif 'mux' in psd_name: # multi-band EPI!
        psd_type = 'muxepi'
    elif 'epi' in psd_name:
        psd_type = 'epi'
    elif psd_name in ['probe-mega','gaba_ss_cni']:
        psd_type = 'mrs'
    elif psd_name == 'asl':
        psd_type = 'asl'
    elif psd_name in ['bravo','3dgrass']:
        psd_type = 'spgr'
    elif psd_name == 'fgre':
        psd_type = 'gre'
    elif psd_name == 'ssfse':
        psd_type = 'fse'
    elif psd_name == 'cube':
        psd_type = 'cube'
    else:
        psd_type = 'unknown'
    #psd_dict = {'ge':{'cube':'cube','ssfse':'fse'}, 'siemens':{}, 'philips':{}}
    return psd_type


class NIMSImageError(nimsdata.NIMSDataError):
    pass


# TODO: pull up common meta-data fields and methods from the subclasses.
class NIMSImage(nimsdata.NIMSData):

    __metaclass__ = abc.ABCMeta

    datakind = u'raw'
    datatype = u'mri'

    epoch_fields = nimsdata.NIMSData.epoch_fields + [
            ('psd', 'psd'),
            ('tr', 'tr'),
            ('te', 'te'),
            ('ti', 'ti'),
            ('flip_angle', 'flip_angle'),
            ('pixel_bandwidth', 'pixel_bandwidth'),
            ('num_slices', 'num_slices'),
            ('num_timepoints', 'num_timepoints'),
            ('num_averages', 'num_averages'),
            ('num_echos', 'num_echos'),
            ('receive_coil', 'receive_coil_name'),
            ('num_receivers', 'num_receivers'),
            ('protocol', 'protocol_name'),
            ('scanner', 'scanner_name'),
            ('size_x', 'size_x'),
            ('size_y', 'size_y'),
            ('fov', 'fov'),
            ('scan_type', 'scan_type'),
            ('num_bands', 'num_bands'),
            #('prescribed_duration', 'prescribed_duration'), #FIXME: mongo can't serialize datetime.timedelta
            ('mm_per_voxel', 'mm_per_vox'),
            ('effective_echo_spacing', 'effective_echo_spacing'),
            ('phase_encode_undersample', 'phase_encode_undersample'),
            ('slice_encode_undersample', 'slice_encode_undersample'),
            ('acquisition_matrix', 'acquisition_matrix'),
            ]

    @abc.abstractmethod
    def __init__(self):
        super(NIMSImage, self).__init__()

    @abc.abstractmethod
    def load_all_metadata(self):
        pass

    @abc.abstractmethod
    def get_imagedata(self):
        pass

    @abc.abstractmethod
    def convert(self, outbase, *args, **kwargs):
        pass

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
            scan_type = scan_types.spectroscopy
        elif self.psd_type == 'asl':
            scan_type = scan_types.perfusion
        elif self.psd_type == 'hoshim':
            scan_type = scan_types.shim
        elif self.is_dwi:
            scan_type = scan_types.diffusion
        elif self.psd_type == 'spiral' and self.num_timepoints == 2 and self.te < .05:
            scan_type = scan_types.fieldmap
        elif 'epi' in self.psd_type and self.te>0.02 and self.te<0.05 and self.num_timepoints>2:
            scan_type = scan_types.functional
        elif (self.psd_type=='gre' or self.psd_type=='fse') and self.fov[0]>=250. and self.fov[1]>=250. and self.mm_per_vox[2]>=5.:
            # Could be either a low-res calibration scan (e.g., ASSET cal) or a localizer.
            if self.mm_per_vox[0] > 2:
                scan_type = scan_types.calibration
            else:
                scan_type = scan_types.localizer
        else:
            # anything else will be an anatomical
            if self.psd_type == 'spgr':
                scan_type = scan_types.anatomy_t1w
            elif self.psd_type == 'cube':
                scan_type = scan_types.anatomy_t2w
            else:
                scan_type = scan_types.anatomy
        return scan_type

    def get_slice_order(self):
        if self.slice_order==None:
            self.load_all_metadata()
        if self.slice_order==SLICE_ORDER_ALT_INC:
            slice_order = np.hstack((np.arange(0,self.num_slices,2), np.arange(1,self.num_slices,2)))
        elif self.slice_order==SLICE_ORDER_ALT_DEC:
            slice_order = np.hstack((np.arange(0,self.num_slices,2), np.arange(1,self.num_slices,2)))[::-1]
        elif self.slice_order==SLICE_ORDER_SEQ_INC:
            slice_order = np.arange(0, self.num_slices)
        elif self.slice_order==SLICE_ORDER_SEQ_DEC:
            slice_order = np.arange(0, self.num_slices)[::-1]
        elif self.slice_order==SLICE_ORDER_UNKNOWN or self.slice_order==None:
            slice_order = None
        return slice_order
