#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer
#           Bob Dougherty

from __future__ import print_function

import os
import signal
import tarfile
import argparse
import datetime
import cStringIO

import dicom
import numpy as np
import nibabel

import nimsutil
import png

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

SLICE_ORDER_UNKNOWN = 0
SLICE_ORDER_SEQ_INC = 1
SLICE_ORDER_SEQ_DEC = 2
SLICE_ORDER_ALT_INC = 3
SLICE_ORDER_ALT_DEC = 4


class DicomError(Exception):
    pass


class DicomAcquisition(object):
    filetype = u'dicom'
    priority = 0

    def __init__(self, dcm_path, log=None):
        def acq_date(dcm):
            if 'AcquisitionDate' in dcm:    return dcm.AcquisitionDate
            elif 'StudyDate' in dcm:        return dcm.StudyDate
            else:                           return '19000101'

        def acq_time(dcm):
            if 'AcquisitionTime' in dcm:    return dcm.AcquisitionTime
            elif 'StudyTime' in dcm:        return dcm.StudyTime
            else:                           return '000000'

        self.dcm_path = dcm_path
        self.dcm_list = None
        self.log = log
        try:
            dcm = self.load_first_dicom()
        except (IOError, dicom.filereader.InvalidDicomError):
            raise DicomError
        else:
            self.exam_no = int(dcm.StudyID)
            self.series_no = int(dcm.SeriesNumber)
            self.acq_no = int(dcm.AcquisitionNumber) if 'AcquisitionNumber' in dcm else 0
            self.exam_uid = dcm.StudyInstanceUID
            self.series_uid = dcm.SeriesInstanceUID
            self.series_desc = dcm.SeriesDescription
            self.patient_id = dcm.PatientID
            self.subj_fn, self.subj_ln, self.subj_dob = nimsutil.parse_subject(dcm.PatientName, dcm.PatientBirthDate)
            self.psd_name = os.path.basename(dcm[TAG_PSD_NAME].value) if TAG_PSD_NAME in dcm else 'unknown'
            self.scan_type = dcm[TAG_PSD_INAME].value if TAG_PSD_INAME in dcm else 'unknown'
            self.physio_flag = 'epi' in self.psd_name.lower()
            self.timestamp = datetime.datetime.strptime(acq_date(dcm) + acq_time(dcm), '%Y%m%d%H%M%S')

            self.ti = float(getattr(dcm, 'InversionTime', 0.0)) / 1000.0
            self.te = float(getattr(dcm, 'EchoTime', 0.0)) / 1000.0
            self.tr = float(getattr(dcm, 'RepetitionTime', 0.0)) / 1000.0
            self.flip_angle = float(getattr(dcm, 'FlipAngle', 0.0))
            self.pixel_bandwidth = float(getattr(dcm, 'PixelBandwidth', 0.0))
            self.phase_encode = 1 if 'InPlanePhaseEncodingDirection' in dcm and dcm.InPlanePhaseEncodingDirection == 'COL' else 0
            self.mt_offset_hz = float(dcm[TAG_MTOFF_HZ].value) if TAG_MTOFF_HZ in dcm else 0.0

            self.total_num_slices = int(getattr(dcm, 'ImagesInAcquisition', 0))
            self.num_slices = int(dcm[TAG_SLICES_PER_VOLUME].value) if TAG_SLICES_PER_VOLUME in dcm else 1
            self.num_timepoints = int(getattr(dcm, 'NumberOfTemporalPositions', self.total_num_slices / self.num_slices))
            self.num_averages = int(getattr(dcm, 'NumberOfAverages', 1))
            self.num_echos = int(getattr(dcm, 'EchoNumbers', 1))
            self.receive_coil_name = getattr(dcm, 'ReceiveCoilName', 'unknown')
            self.num_receivers = 0 # FIXME: where is this stored?
            self.prescribed_duration = datetime.timedelta(0, self.tr * self.num_timepoints * self.num_averages) # FIXME: probably need more hacks in here to compute the correct duration.
            self.duration = self.prescribed_duration # The actual duration can only be computed after the data are loaded. Settled for rx duration for now.
            self.operator = getattr(dcm, 'OperatorsName', 'unknown')
            self.protocol_name = getattr(dcm, 'ProtocolName', 'unknown')
            self.scanner_name = '%s %s'.strip() % (getattr(dcm, 'InstitutionName', ''), getattr(dcm, 'StationName', ''))
            self.scanner_type = '%s %s'.strip() % (getattr(dcm, 'Manufacturer', ''), getattr(dcm, 'ManufacturerModelName', ''))
            self.acquisition_type = getattr(dcm, 'MRAcquisitionType', 'unknown')
            self.mm_per_vox = [float(i) for i in dcm.PixelSpacing + [dcm.SpacingBetweenSlices]] if 'PixelSpacing' in dcm and 'SpacingBetweenSlices' in dcm else [0.0, 0.0, 0.0]
            # FIXME: confirm that DICOM (Columns,Rows) = PFile (X,Y)
            self.size_x = int(getattr(dcm, 'Columns', 0))
            self.size_y = int(getattr(dcm, 'Rows', 0))
            self.fov = [float(dcm.ReconstructionDiameter), float(dcm.ReconstructionDiameter)] if 'ReconstructionDiameter' in dcm else [0.0, 0.0]
            # Dicom convention is ROW,COL. E.g., ROW is the first dim (index==0), COL is the second (index==1)
            if self.phase_encode == 1:
                # The Acquisition matrix field includes four values: [freq rows, freq columns, phase rows, phase columns].
                # E.g., for a 64x64 image, it would be [64,0,0,64] if the image row axis was the frequency encoding axis or
                # [0,64,64,0] if the image row was the phase encoding axis. We'll just save all four values.
                self.acquisition_matrix = dcm.AcquisitionMatrix[0:4:3] if 'AcquisitionMatrix' in dcm else [0,0]
                if 'PercentPhaseFieldOfView' in dcm:
                    self.fov[1] = self.fov[1] / (float(dcm.PercentPhaseFieldOfView)/100.)
            else:
                # We want the acq matrix to always be ROWS,COLS, so we flip the order for the case where the phase encode is the first dim:
                self.acquisition_matrix = dcm.AcquisitionMatrix[2:0:-1] if 'AcquisitionMatrix' in dcm else [0,0]
                if 'PercentPhaseFieldOfView' in dcm:
                    self.fov[0] = self.fov[0] / (float(dcm.PercentPhaseFieldOfView)/100.)

            if 'ImageType' in dcm and dcm.ImageType==TYPE_ORIGINAL and TAG_DIFFUSION_DIRS in dcm and dcm[TAG_DIFFUSION_DIRS].value >= 6:
                self.diffusion_flag = True
            else:
                self.diffusion_flag = False
            self.effective_echo_spacing = float(dcm[TAG_EPI_EFFECTIVE_ECHO_SPACING].value)/1.0e6 if TAG_EPI_EFFECTIVE_ECHO_SPACING in dcm else 0.0
            # The R-factor (phase/slice undersample) field usualy contains a list of length 2, with each element containing
            # a string that represents a float. But these two floats have been known to be stuffed into a single string,
            # separated by two slashes (e.g., in a GE "Cerebral Blood Flow" image derived from and ASL scan).
            if TAG_PHASE_ENCODE_UNDERSAMPLE in dcm and isinstance(dcm[TAG_PHASE_ENCODE_UNDERSAMPLE].value, list):
                r = dcm[TAG_PHASE_ENCODE_UNDERSAMPLE].value
            elif TAG_PHASE_ENCODE_UNDERSAMPLE in dcm and isinstance(dcm[TAG_PHASE_ENCODE_UNDERSAMPLE].value, str):
                r = dcm[TAG_PHASE_ENCODE_UNDERSAMPLE].value.split('\\')
            else:
                r = [1.,1.]
            self.phase_encode_undersample = float(r[0])
            self.slice_encode_undersample = float(r[1])
            # Assume that dicoms are never multiband
            self.num_bands = 1
            self.image_type = getattr(dcm, 'ImageType', None)
            self.cosines = getattr(dcm, 'ImageOrientationPatient', [None,None,None,None,None,None])

    def load_first_dicom(self):
        if os.path.isfile(self.dcm_path) and tarfile.is_tarfile(self.dcm_path):
            with tarfile.open(self.dcm_path) as archive:
                archive.next()  # skip over top-level directory
                dcm = dicom.read_file(cStringIO.StringIO(archive.extractfile(archive.next()).read()), stop_before_pixels=True)
            self.compressed = True
        elif os.path.isfile(self.dcm_path):
            # A single dicom file
            dcm = dicom.read_file(self.dcm_path, stop_before_pixels=True)
            self.compressed = False
        else:
            # Assume it's a directory of dicoms
            dcm = dicom.read_file(os.path.join(self.dcm_path, os.listdir(self.dcm_path)[0]), stop_before_pixels=True)
            self.compressed = False
        if dcm.Manufacturer != 'GE MEDICAL SYSTEMS':    # TODO: make code more general
            raise DicomError
        return dcm

    def load_all_dicoms(self):
        if os.path.isfile(self.dcm_path) and tarfile.is_tarfile(self.dcm_path):
            with tarfile.open(self.dcm_path) as archive:
                archive.next()  # skip over top-level directory
                dcm_list = [dicom.read_file(cStringIO.StringIO(archive.extractfile(ti).read())) for ti in archive]  # dead-slow w/o StringIO
        elif os.path.isfile(self.dcm_path):
            dcm_list = [dicom.read_file(self.dcm_path)]
        else:
            dcm_list = [dicom.read_file(os.path.join(self.dcm_path, f)) for f in os.listdir(self.dcm_path)]
        self.dcm_list = sorted(dcm_list, key=lambda dcm: dcm.InstanceNumber)

    def convert(self, outbase):
        self.dcm_list or self.load_all_dicoms()
        result = (None, None)
        if not self.image_type:
            # *** Should we raise an exception here? (Old code did) ***
            msg = 'dicom conversion failed for %s: ImageType not set in dicom header' % os.path.basename(outbase)
            self.log.warning(msg) if self.log else print(msg)
        else:
            if self.image_type == TYPE_SCREEN:
                self._to_img(outbase)
                result = ('bitmap', None)
            if self.diffusion_flag:
                self._to_dti(outbase)
                result = ('nifti', None)
            if 'PRIMARY' in self.image_type:
                result = ('nifti', self._to_nii(outbase))
            if result[0] is None:
                msg = 'dicom conversion failed for %s: no applicable conversion defined' % os.path.basename(outbase)
                self.log.warning(msg) if self.log else print(msg)
        return result

    def _to_img(self, outbase):
        """Create bitmap files for each image in a list of dicoms."""
        for i, pixels in enumerate([dcm.pixel_array for dcm in self.dcm_list]):
            filename = outbase + '_%d.png' % (i+1)
            with open(filename, 'wb') as fd:
                if pixels.ndim == 2:
                    pixels = pixels.astype(np.int)
                    pixels = pixels.clip(0, (pixels * (pixels != (2**15 - 1))).max())   # -32768->0; 32767->brain.max
                    pixels = pixels * (2**16 -1) / pixels.max()                         # scale to full 16-bit range
                    png.Writer(size=pixels.shape, greyscale=True, bitdepth=16).write(fd, pixels)
                elif pixels.ndim == 3:
                    pixels = pixels.flatten().reshape((pixels.shape[1], pixels.shape[0]*pixels.shape[2]))
                    png.Writer(pixels.shape[0], pixels.shape[1]/3).write(fd, pixels)
            self.log and self.log.debug('generated %s' % os.path.basename(filename))

    def _to_dti(self, outbase):
        """Create bval and bvec files from an ordered list of dicoms."""
        images_per_volume = self.dcm_list[0][TAG_SLICES_PER_VOLUME].value
        bvals = np.array([dcm[TAG_BVALUE].value[0] for dcm in self.dcm_list[0::images_per_volume]], dtype=float)
        bvecs = np.array([(dcm[TAG_BVEC[0]].value, dcm[TAG_BVEC[1]].value, dcm[TAG_BVEC[2]].value) for dcm in self.dcm_list[0::images_per_volume]]).transpose()
        filename = outbase + '.bval'
        with open(filename, 'w') as bvals_file:
            bvals_file.write(' '.join(['%f' % value for value in bvals]))
        self.log and self.log.debug('generated %s' % os.path.basename(filename))
        filename = outbase + '.bvec'
        with open(filename, 'w') as bvecs_file:
            bvecs_file.write(' '.join(['%f' % value for value in bvecs[0,:]]) + '\n')
            bvecs_file.write(' '.join(['%f' % value for value in bvecs[1,:]]) + '\n')
            bvecs_file.write(' '.join(['%f' % value for value in bvecs[2,:]]) + '\n')
        self.log and self.log.debug('generated %s' % os.path.basename(filename))

    def _to_nii(self, outbase):
        """Create a single nifti file from an ordered list of dicoms."""
        notes_filename = outbase + '_README.txt'
        flipped = False
        slice_loc = [dcm_i.SliceLocation for dcm_i in self.dcm_list]
        slice_num = [dcm_i.InstanceNumber for dcm_i in self.dcm_list]
        image_position = [tuple(dcm_i.ImagePositionPatient) for dcm_i in self.dcm_list]
        image_data = np.dstack([np.swapaxes(dcm_i.pixel_array, 0, 1) for dcm_i in self.dcm_list])

        unique_slice_pos = np.unique(image_position).astype(np.float)
        slices_per_volume = len(unique_slice_pos) # also: image[TAG_SLICES_PER_VOLUME].value
        num_volumes = self.total_num_slices / slices_per_volume
        if num_volumes == 1:
            # crude check for a 3-plane localizer. When we get one of these, we actually
            # want each plane to be a different time point.
            d = np.sqrt((np.diff(unique_slice_pos,axis=0)**2).sum(1))
            num_volumes = np.sum((d - np.median(d)) > 10) + 1
            slices_per_volume = self.total_num_slices / num_volumes
        dims = np.array((self.size_y, self.size_x, slices_per_volume, num_volumes))
        slices_total = len(self.dcm_list)

        # If we can figure the dimensions out, reshape the matrix
        if np.prod(dims) == np.size(image_data):
            image_data = image_data.reshape(dims, order='F')
        else:
            self.log and self.log.debug("dimensions inconsistent with size, attempting to construct volume")
            # round up slices to nearest multiple of slices_per_volume
            slices_total_rounded_up = ((slices_total + slices_per_volume - 1) / slices_per_volume) * slices_per_volume
            slices_padding = slices_total_rounded_up - slices_total
            if slices_padding: #LOOK AT THIS MORE CLOSELY TODO
                msg = "dimensions indicate missing slices from volume - zero padding with %d slices." % slices_padding
                self.log.warning(msg) if self.log else print(msg)
                with open(notes_filename, 'at') as fp:
                    fp.write('WARNING: ' + msg + '\n')
                padding = np.zeros((self.size_y, self.size_x, slices_padding))
                image_data = np.dstack([image_data, padding])
            volume_start_indices = range(0, slices_total_rounded_up, slices_per_volume)
            image_data = np.concatenate([image_data[:,:,index:(index + slices_per_volume),np.newaxis] for index in volume_start_indices], axis=3)

        # Check for multi-echo data where duplicate slices might be interleaved
        # TODO: we only handle the 4d case here, but this could in theory happen with others.
        # TODO: it's inefficient to reshape the array above and *then* check to see if
        #       that shape is wrong. The reshape op is expensive, and to fix the shape requires
        #       an expensive loop and a copy of the data, which doubles memory usage. Instead, try
        #       to do the de-interleaving up front in the beginning.
        if num_volumes>1 and slice_loc[0::num_volumes]==slice_loc[1::num_volumes] and image_data.ndim==4:
            # If a scan was aborted, the number of volumes might be less than the target number of
            # volumes (num_volumes). We'll zero-pad in that case.
            if image_data.shape[3] < num_volumes:
                pad_vols = num_volumes - image_data.shape[3]
                msg = "dimensions indicate missing data - zero padding with %d volumes." % pad_vols
                self.log.warning(msg) if self.log else print(msg)
                image_data = np.append(image_data, np.zeros(image_data.shape[0:3]+(pad_vols,), dtype=image_data.dtype), axis=3)
                with open(notes_filename, 'at') as fp:
                    fp.write('WARNING: ' + msg + '\n')
            nvols = np.prod(image_data.shape[2:4])
            tmp = image_data.copy().reshape([image_data.shape[0], image_data.shape[1], nvols], order='F')
            for vol_num in range(num_volumes):
                image_data[:,:,:,vol_num] = tmp[:,:,vol_num::num_volumes]

        row_cosines = self.cosines[0:3]
        col_cosines = self.cosines[3:6]
        slice_norm = np.cross(row_cosines, col_cosines)

        qto_xyz = np.zeros((4,4))
        qto_xyz[0,0] = -row_cosines[0]
        qto_xyz[0,1] = -col_cosines[0]
        qto_xyz[0,2] = -slice_norm[0]

        qto_xyz[1,0] = -row_cosines[1]
        qto_xyz[1,1] = -col_cosines[1]
        qto_xyz[1,2] = -slice_norm[1]

        qto_xyz[2,0] = row_cosines[2]
        qto_xyz[2,1] = col_cosines[2]
        qto_xyz[2,2] = slice_norm[2]

        if np.dot(slice_norm, image_position[0]) > np.dot(slice_norm, image_position[-1]):
            self.log and self.log.debug('flipping image order')
            flipped = True
            slice_num = slice_num[::-1]
            slice_loc = slice_loc[::-1]
            image_position = image_position[::-1]
            image_data = image_data[:,:,::-1,:]

        pos = image_position[0]
        qto_xyz[:,3] = np.array((-pos[0], -pos[1], pos[2], 1)).T
        qto_xyz[0:3,0:3] = np.dot(qto_xyz[0:3,0:3], np.diag(self.mm_per_vox))

        nii_header = nibabel.Nifti1Header()
        nii_header.set_xyzt_units('mm', 'sec')
        nii_header.set_qform(qto_xyz, 'scanner')
        nii_header.set_sform(qto_xyz, 'scanner')

        nii_header['slice_start'] = 0
        nii_header['slice_end'] = slices_per_volume - 1
        slice_order = SLICE_ORDER_UNKNOWN
        if slices_total >= slices_per_volume and 'TriggerTime' in self.dcm_list[0] and self.dcm_list[0].TriggerTime != '':
            first_volume = self.dcm_list[0:slices_per_volume]
            trigger_times = np.array([dcm_i.TriggerTime for dcm_i in first_volume])
            trigger_times_from_first_slice = trigger_times[0] - trigger_times
            if slices_per_volume > 2:
                nii_header['slice_duration'] = float(min(abs(trigger_times_from_first_slice[1:]))) / 1000.  # msec to sec
                if trigger_times_from_first_slice[1] < 0:
                    slice_order = SLICE_ORDER_SEQ_INC if trigger_times[2] > trigger_times[1] else SLICE_ORDER_ALT_INC
                else:
                    slice_order = SLICE_ORDER_ALT_DEC if trigger_times[2] > trigger_times[1] else SLICE_ORDER_SEQ_DEC
            else:
                nii_header['slice_duration'] = trigger_times[0]
                slice_order = SLICE_ORDER_SEQ_INC
        nii_header['slice_code'] = slice_order

        if self.phase_encode == 0: # self[TAG_PHASE_ENCODE_DIR].value == 'ROWS':
            fps_dim = [1, 0, 2]
        else:
            fps_dim = [0, 1, 2]
        nii_header.set_dim_info(*fps_dim)

        nii_header.structarr['pixdim'][4] = self.tr

        if image_data.dtype == np.dtype('int16'):
            nii_header.set_data_dtype(np.int16)

        # Let's stuff some extra data into the description field (max of 80 chars)
        nii_header['descrip'] = 'te=%.2f;ti=%.0f;fa=%.0f;ec=%.4f;acq=[%s];mt=%.0f;rp=%.1f;' % (
                                 self.te * 1000.,
                                 self.ti * 1000.,
                                 self.flip_angle,
                                 self.effective_echo_spacing * 1000.,
                                 ','.join(map(str, self.acquisition_matrix)),
                                 self.mt_offset_hz,
                                 1. / self.phase_encode_undersample)
        # For 3D acquisitions, we'll add the slice R-factor
        if '3D' in self.acquisition_type:
            nii_header['descrip'] = str(nii_header['descrip']) + 'rs=%.1f' % (1. / self.slice_encode_undersample)

        # Other unused fields: nii_header['data_type'] (10 chars), nii_header['db_name'] (18 chars),

        nifti = nibabel.Nifti1Image(image_data, None, nii_header)
        filename = outbase + '.nii.gz'
        nibabel.save(nifti, filename)
        self.log and self.log.debug('generated %s' % os.path.basename(filename))
        return filename


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Convert a directory of dicom images to a NIfTI or bitmap."""
        self.add_argument('dcm_dir', help='directory of dicoms to convert')
        self.add_argument('outbase', nargs='?', help='basename for output files (default: dcm_dir)')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    dcm_acq = DicomAcquisition(args.dcm_dir)
    dcm_acq.convert(args.outbase or os.path.basename(args.dcm_dir.rstrip('/')))
