#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer
#           Bob Dougherty

import os
import dicom
import logging
import tarfile
import argparse
import datetime
import cStringIO
import numpy as np

import nimspng
import nimsutil
import nimsimage
import nimsnifti

log = logging.getLogger('nimsdicom')

dicom.config.enforce_valid_values = False

TYPE_ORIGINAL = ['ORIGINAL', 'PRIMARY', 'OTHER']
TYPE_EPI =      ['ORIGINAL', 'PRIMARY', 'EPI', 'NONE']
TYPE_SCREEN =   ['DERIVED', 'SECONDARY', 'SCREEN SAVE']

TAG_PSD_NAME =          (0x0019, 0x109c)
TAG_PSD_INAME =         (0x0019, 0x109e)
TAG_PHASE_ENCODE_DIR =  (0x0018, 0x1312)
TAG_EPI_EFFECTIVE_ECHO_SPACING = (0x0043, 0x102c)
TAG_PHASE_ENCODE_UNDERSAMPLE = (0x0043, 0x1083)
TAG_SLICES_PER_VOLUME = (0x0021, 0x104f)
TAG_DIFFUSION_DIRS =    (0x0019, 0x10e0)
TAG_BVALUE =            (0x0043, 0x1039)
TAG_BVEC =              [(0x0019, 0x10bb), (0x0019, 0x10bc), (0x0019, 0x10bd)]
TAG_MTOFF_HZ =          (0x0043, 0x1034)


def getelem(hdr, tag, type_=None, default=None):
    try:
        value = getattr(hdr, tag) if isinstance(tag, basestring) else hdr[tag].value
        if type_ is not None:
            value = [type_(x) for x in value] if isinstance(value, list) else type_(value)
    except (AttributeError, KeyError, ValueError):
        value = default
    return value


class NIMSDicomError(nimsimage.NIMSImageError):
    pass


class NIMSDicom(nimsimage.NIMSImage):

    filetype = u'dicom'
    priority = 0
    parse_priority = 9

    def __init__(self, dcm_path):
        self.dcm_path = dcm_path

        def acq_date(hdr):
            if 'AcquisitionDate' in hdr:    return hdr.AcquisitionDate
            elif 'StudyDate' in hdr:        return hdr.StudyDate
            else:                           return '19000101'

        def acq_time(hdr):
            if 'AcquisitionTime' in hdr:    return hdr.AcquisitionTime
            elif 'StudyTime' in hdr:        return hdr.StudyTime
            else:                           return '000000'

        try:
            if os.path.isfile(self.dcm_path) and tarfile.is_tarfile(self.dcm_path):     # compressed tarball
                self.compressed = True
                with tarfile.open(self.dcm_path) as archive:
                    archive.next()  # skip over top-level directory
                    self._hdr = dicom.read_file(cStringIO.StringIO(archive.extractfile(archive.next()).read()), stop_before_pixels=True)
            else:                                                                       # directory of dicoms or single file
                self.compressed = False
                dcm_path = self.dcm_path if os.path.isfile(self.dcm_path) else os.path.join(self.dcm_path, os.listdir(self.dcm_path)[0])
                self._hdr = dicom.read_file(dcm_path, stop_before_pixels=True)
            if self._hdr.Manufacturer != 'GE MEDICAL SYSTEMS':    # TODO: make code more general
                raise NIMSDicomError('we can only handle data from GE MEDICAL SYSTEMS')
        except Exception as e:
            raise NIMSDicomError(e)

        self.exam_no = getelem(self._hdr, 'StudyID', int)
        self.series_no = getelem(self._hdr, 'SeriesNumber', int)
        self.acq_no = getelem(self._hdr, 'AcquisitionNumber', int, 0)
        self.exam_uid = getelem(self._hdr, 'StudyInstanceUID')
        self.series_uid = getelem(self._hdr, 'SeriesInstanceUID')
        self.series_desc = getelem(self._hdr, 'SeriesDescription')
        self.patient_id = getelem(self._hdr, 'PatientID')
        self.subj_firstname, self.subj_lastname = self.parse_subject_name(getelem(self._hdr, 'PatientName', None, ''))
        self.subj_dob = self.parse_subject_dob(getelem(self._hdr, 'PatientBirthDate', None, ''))
        self.subj_sex = {'M': 'male', 'F': 'female'}.get(getelem(self._hdr, 'PatientSex'))
        self.psd_name = os.path.basename(getelem(self._hdr, TAG_PSD_NAME, None, 'unknown'))
        self.scan_type = getelem(self._hdr, TAG_PSD_INAME, None, 'unknown')
        self.timestamp = datetime.datetime.strptime(acq_date(self._hdr) + acq_time(self._hdr), '%Y%m%d%H%M%S')
        self.ti = getelem(self._hdr, 'InversionTime', float, 0.) / 1000.0
        self.te = getelem(self._hdr, 'EchoTime', float, 0.) / 1000.0
        self.tr = getelem(self._hdr, 'RepetitionTime', float, 0.) / 1000.0
        self.flip_angle = getelem(self._hdr, 'FlipAngle', float, 0.)
        self.pixel_bandwidth = getelem(self._hdr, 'PixelBandwidth', float, 0.)
        self.phase_encode = int(getelem(self._hdr, 'InPlanePhaseEncodingDirection', None, '') == 'COL')
        self.mt_offset_hz = getelem(self._hdr, TAG_MTOFF_HZ, float, 0.)
        self.total_num_slices = getelem(self._hdr, 'ImagesInAcquisition', int, 0)
        self.num_slices = getelem(self._hdr, TAG_SLICES_PER_VOLUME, int, 1)
        self.num_timepoints = getelem(self._hdr, 'NumberOfTemporalPositions', int, self.total_num_slices / self.num_slices)
        self.num_averages = getelem(self._hdr, 'NumberOfAverages', int, 1)
        self.num_echos = getelem(self._hdr, 'EchoNumbers', int, 1)
        self.receive_coil_name = getelem(self._hdr, 'ReceiveCoilName', None, 'unknown')
        self.num_receivers = 0 # FIXME: where is this stored?
        self.prescribed_duration = datetime.timedelta(0, self.tr * self.num_timepoints * self.num_averages) # FIXME: probably need more hacks in here to compute the correct duration.
        self.duration = self.prescribed_duration # actual duration can only be computed after all data are loaded
        self.operator = getelem(self._hdr, 'OperatorsName', None, 'unknown')
        self.protocol_name = getelem(self._hdr, 'ProtocolName', None, 'unknown')
        self.scanner_name = '%s %s'.strip() % (getelem(self._hdr, 'InstitutionName', None, ''), getelem(self._hdr, 'StationName', None, ''))
        self.scanner_type = '%s %s'.strip() % (getelem(self._hdr, 'Manufacturer', None, ''), getelem(self._hdr, 'ManufacturerModelName', None, ''))
        self.acquisition_type = getelem(self._hdr, 'MRAcquisitionType', None, 'unknown')
        self.mm_per_vox = getelem(self._hdr, 'PixelSpacing', float, [0., 0.]) + [getelem(self._hdr, 'SpacingBetweenSlices', float, 0.)]
        # FIXME: confirm that DICOM (Columns,Rows) = PFile (X,Y)
        self.size_x = getelem(self._hdr, 'Columns', int, 0)
        self.size_y = getelem(self._hdr, 'Rows', int, 0)
        self.fov = 2 * [getelem(self._hdr, 'ReconstructionDiameter', float, 0.)]
        # Dicom convention is ROW,COL. E.g., ROW is the first dim (index==0), COL is the second (index==1)
        if self.phase_encode == 1:
            # The Acquisition matrix field includes four values: [freq rows, freq columns, phase rows, phase columns].
            # E.g., for a 64x64 image, it would be [64,0,0,64] if the image row axis was the frequency encoding axis or
            # [0,64,64,0] if the image row was the phase encoding axis.
            self.acquisition_matrix = getelem(self._hdr, 'AcquisitionMatrix', None, [0, 0, 0, 0])[0:4:3]
            self.fov[1] /= (getelem(self._hdr, 'PercentPhaseFieldOfView', float, 0.) / 100.) if 'PercentPhaseFieldOfView' in self._hdr else 1.
        else:
            # We want the acq matrix to always be ROWS,COLS, so we flip the order for the case where the phase encode is the first dim:
            self.acquisition_matrix = getelem(self._hdr, 'AcquisitionMatrix', None, [0, 0, 0, 0])[2:0:-1]
            self.fov[0] /= (getelem(self._hdr, 'PercentPhaseFieldOfView', float, 0.) / 100.) if 'PercentPhaseFieldOfView' in self._hdr else 1.
        r = getelem(self._hdr, TAG_PHASE_ENCODE_UNDERSAMPLE, None, [1., 1.])
        self.phase_encode_undersample, self.slice_encode_undersample = [float(x) for x in (r.split('\\') if isinstance(r, basestring) else r)]
        self.num_bands = 1 # assume that dicoms are never multiband
        cosines = getelem(self._hdr, 'ImageOrientationPatient', None, 6 * [None])
        self.row_cosines = cosines[0:3]
        self.col_cosines = cosines[3:6]
        self.slice_norm = np.cross(self.row_cosines, self.col_cosines) if any(cosines) else np.zeros(3)
        self.image_type = getelem(self._hdr, 'ImageType', None, [])
        self.effective_echo_spacing = getelem(self._hdr, TAG_EPI_EFFECTIVE_ECHO_SPACING, float, 0.) / 1e6
        self.is_dwi = bool(self.image_type == TYPE_ORIGINAL and getelem(self._hdr, TAG_DIFFUSION_DIRS, int, 0) >= 6)
        self.bvals = None
        self.bvecs = None
        self.notes = ''
        super(NIMSDicom, self).__init__()

    def parse_all_dicoms(self, dcm_list):
        if self.is_dwi:
            self.bvals = np.array([getelem(dcm, TAG_BVALUE, float)[0] for dcm in dcm_list[0::self.num_slices]])
            self.bvecs = np.array([[getelem(dcm, TAG_BVEC[i], float) for i in range(3)] for dcm in dcm_list[0::self.num_slices]]).transpose()
        slice_loc = [getelem(dcm, 'SliceLocation') for dcm in dcm_list]
        slice_num = [getelem(dcm, 'InstanceNumber') for dcm in dcm_list]
        image_position = [tuple(getelem(dcm, 'ImagePositionPatient', None, [0, 0, 0])) for dcm in dcm_list]
        imagedata = np.dstack([np.swapaxes(dcm.pixel_array, 0, 1) for dcm in dcm_list])

        unique_slice_pos = np.unique(image_position).astype(np.float)
        if self.num_timepoints == 1:
            # crude check for a 3-plane localizer. When we get one of these, we actually
            # want each plane to be a different time point.
            d = np.sqrt((np.diff(unique_slice_pos,axis=0)**2).sum(1))
            self.num_timepoints = np.sum((d - np.median(d)) > 10) + 1
            self.num_slices = self.total_num_slices / self.num_timepoints
        dims = np.array((self.size_y, self.size_x, self.num_slices, self.num_timepoints))
        slices_total = len(dcm_list)

        # If we can figure the dimensions out, reshape the matrix
        if np.prod(dims) == np.size(imagedata):
            imagedata = imagedata.reshape(dims, order='F')
        else:
            log.debug('dimensions inconsistent with size, attempting to construct volume')
            # round up slices to nearest multiple of self.num_slices
            slices_total_rounded_up = ((slices_total + self.num_slices - 1) / self.num_slices) * self.num_slices
            slices_padding = slices_total_rounded_up - slices_total
            if slices_padding: #LOOK AT THIS MORE CLOSELY TODO
                msg = 'dimensions indicate missing slices from volume - zero padding with %d slices' % slices_padding
                self.notes += 'WARNING: ' + msg + '\n'
                log.warning(msg)
                padding = np.zeros((self.size_y, self.size_x, slices_padding))
                imagedata = np.dstack([imagedata, padding])
            volume_start_indices = range(0, slices_total_rounded_up, self.num_slices)
            imagedata = np.concatenate([imagedata[:,:,index:(index + self.num_slices),np.newaxis] for index in volume_start_indices], axis=3)

        # Check for multi-echo data where duplicate slices might be interleaved
        # TODO: we only handle the 4d case here, but this could in theory happen with others.
        # TODO: it's inefficient to reshape the array above and *then* check to see if
        #       that shape is wrong. The reshape op is expensive, and to fix the shape requires
        #       an expensive loop and a copy of the data, which doubles memory usage. Instead, try
        #       to do the de-interleaving up front in the beginning.
        if self.num_timepoints>1 and slice_loc[0::self.num_timepoints]==slice_loc[1::self.num_timepoints] and imagedata.ndim==4:
            # If a scan was aborted, the number of volumes might be less than the target number of
            # volumes (self.num_timepoints). We'll zero-pad in that case.
            if imagedata.shape[3] < self.num_timepoints:
                msg = 'dimensions indicate missing data - zero padding with %d volumes' % pad_vols
                self.notes += 'WARNING: ' + msg + '\n'
                log.warning(msg)
                pad_vols = self.num_timepoints - imagedata.shape[3]
                imagedata = np.append(imagedata, np.zeros(imagedata.shape[0:3]+(pad_vols,), dtype=imagedata.dtype), axis=3)
            nvols = np.prod(imagedata.shape[2:4])
            tmp = imagedata.copy().reshape([imagedata.shape[0], imagedata.shape[1], nvols], order='F')
            for vol_num in range(self.num_timepoints):
                imagedata[:,:,:,vol_num] = tmp[:,:,vol_num::self.num_timepoints]

        self.slice_order = nimsimage.SLICE_ORDER_UNKNOWN
        if slices_total >= self.num_slices and getelem(dcm_list[0], 'TriggerTime', float) is not None:
            trigger_times = np.array([getelem(dcm, 'TriggerTime', float) for dcm in dcm_list[0:self.num_slices]])
            trigger_times_from_first_slice = trigger_times[0] - trigger_times
            if self.num_slices > 2:
                self.slice_duration = float(min(abs(trigger_times_from_first_slice[1:]))) / 1000.  # msec to sec
                if trigger_times_from_first_slice[1] < 0:
                    self.slice_order = nimsimage.SLICE_ORDER_SEQ_INC if trigger_times[2] > trigger_times[1] else nimsimage.SLICE_ORDER_ALT_INC
                else:
                    self.slice_order = nimsimage.SLICE_ORDER_ALT_DEC if trigger_times[2] > trigger_times[1] else nimsimage.SLICE_ORDER_SEQ_DEC
            else:
                self.slice_duration = trigger_times[0]
                self.slice_order = nimsimage.SLICE_ORDER_SEQ_INC
        else:
            self.slice_duration = None

        if np.dot(self.slice_norm, image_position[0]) > np.dot(self.slice_norm, image_position[-1]):
            log.debug('flipping image order')
            slice_num = slice_num[::-1]
            slice_loc = slice_loc[::-1]
            image_position = image_position[::-1]
            imagedata = imagedata[:,:,::-1,:]
        self.image_position = image_position[0] * np.array([-1, -1, 1])
        return imagedata

    def load_all_dicoms(self):
        if os.path.isfile(self.dcm_path) and tarfile.is_tarfile(self.dcm_path):     # compressed tarball
            with tarfile.open(self.dcm_path) as archive:
                dcm_list = [dicom.read_file(cStringIO.StringIO(archive.extractfile(ti).read())) for ti in archive if ti.isreg()]
        elif os.path.isfile(self.dcm_path):                                         # single file
            dcm_list = [dicom.read_file(self.dcm_path)]
        else:                                                                       # directory of dicoms
            dcm_list = [dicom.read_file(os.path.join(self.dcm_path, f)) for f in os.listdir(self.dcm_path)]
        return sorted(dcm_list, key=lambda dcm: dcm.InstanceNumber)

    def convert(self, outbase, *args, **kwargs):
        if not self.image_type:
            log.warning('dicom conversion failed for %s: ImageType not set in dicom header' % os.path.basename(outbase))
            return
        result = (None, None)
        if self.image_type == TYPE_SCREEN:
            for i, dcm in enumerate(self.load_all_dicoms()):
                result = ('bitmap', nimspng.NIMSPNG.write(self, dcm.pixel_array, outbase + '_%d' % (i+1)))
        elif 'PRIMARY' in self.image_type:
            imagedata = self.parse_all_dicoms(self.load_all_dicoms())
            result = ('nifti', nimsnifti.NIMSNifti.write(self, imagedata, outbase, self.notes))
        if result[0] is None:
            log.warning('dicom conversion failed for %s: no applicable conversion defined' % os.path.basename(outbase))
        return result


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Convert a directory of dicom images to a NIfTI or bitmap."""
        self.add_argument('dcm_dir', help='directory of dicoms to convert')
        self.add_argument('outbase', nargs='?', help='basename for output files (default: dcm_dir)')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    nimsutil.configure_log()
    NIMSDicom(args.dcm_dir).convert(args.outbase or os.path.basename(args.dcm_dir.rstrip('/')))
