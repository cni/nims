#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

from __future__ import print_function

import os
import signal
import argparse
import datetime

import dicom
import numpy as np
import nibabel

import png

TYPE_ORIGINAL = ['ORIGINAL', 'PRIMARY', 'OTHER']
TYPE_EPI =      ['ORIGINAL', 'PRIMARY', 'EPI', 'NONE']
TYPE_SCREEN =   ['DERIVED', 'SECONDARY', 'SCREEN SAVE']

TAG_PSD_NAME =          (0x0019, 0x109c)
TAG_PHYSIO_FLAG =       (0x0019, 0x10ac)
TAG_PHASE_ENCODE_DIR =  (0x0018, 0x1312)
TAG_SLICES_PER_VOLUME = (0x0021, 0x104f)
TAG_DIFFUSION_DIRS =    (0x0019, 0x10e0)
TAG_BVALUE =            (0x0043, 0x1039)
TAG_BVEC =              [(0x0019, 0x10bb), (0x0019, 0x10bc), (0x0019, 0x10bd)]

SLICE_ORDER_UNKNOWN = 0
SLICE_ORDER_SEQ_INC = 1
SLICE_ORDER_SEQ_DEC = 2
SLICE_ORDER_ALT_INC = 3
SLICE_ORDER_ALT_DEC = 4


class DicomError(Exception):
    pass


class DicomFile(object):

    def __init__(self, filename):

        def acq_date(dcm):
            if 'AcquisitionDate' in dcm:    return dcm.AcquisitionDate
            elif 'StudyDate' in dcm:        return dcm.StudyDate
            else:                           return '19000101'

        def acq_time(dcm):
            if 'AcquisitionTime' in dcm:    return dcm.AcquisitionTime
            elif 'StudyTime' in dcm:        return dcm.StudyTime
            else:                           return '000000'

        try:
            dcm = dicom.read_file(filename, stop_before_pixels=True)
            if dcm.Manufacturer != 'GE MEDICAL SYSTEMS':    # TODO: make code more general
                raise DicomError
        except (IOError, dicom.filereader.InvalidDicomError):
            raise DicomError
        else:
            self.exam_no = int(dcm.StudyID)
            self.series_no = int(dcm.SeriesNumber)
            self.acq_no = int(dcm.AcquisitionNumber) if 'AcquisitionNumber' in dcm else 0
            self.exam_uid = dcm.StudyInstanceUID
            self.series_uid = dcm.SeriesInstanceUID
            self.psd_name = os.path.basename(dcm[TAG_PSD_NAME].value) if TAG_PSD_NAME in dcm else ''
            self.physio_flag = bool(dcm[TAG_PHYSIO_FLAG].value) if TAG_PHYSIO_FLAG in dcm else False
            self.series_desc = dcm.SeriesDescription
            self.timestamp = datetime.datetime.strptime(acq_date(dcm) + acq_time(dcm), '%Y%m%d%H%M%S')
            self.duration = datetime.timedelta() # FIXME
            self.patient_id = dcm.PatientID
            self.patient_name = dcm.PatientsName
            self.patient_dob = dcm.PatientsBirthDate


class DicomSeries(object):

    def __init__(self, dcm_dir, log=None):
        self.dcm_list = sorted([dicom.read_file(os.path.join(dcm_dir, f)) for f in os.listdir(dcm_dir)], key=lambda dcm: dcm.InstanceNumber)
        self.first_dcm = self.dcm_list[0]
        self.log = log

    def convert(self, outbase):
        result = None
        main_file = None
        try:
            image_type = self.first_dcm.ImageType
        except:
            msg = 'dicom conversion failed for %s: ImageType not set in dicom header' % os.path.basename(outbase)
            self.log and self.log.warning(msg) or print(msg)
        else:
            if image_type == TYPE_SCREEN:
                self.to_img(outbase)
                result = 'bitmap'
            if image_type == TYPE_ORIGINAL and TAG_DIFFUSION_DIRS in self.first_dcm and self.first_dcm[TAG_DIFFUSION_DIRS].value > 0:
                self.to_dti(outbase)
                result = 'dti'
            if 'PRIMARY' in image_type:
                main_file = self.to_nii(outbase)
                result = 'nifti'
            if not result:
                msg = 'dicom conversion failed for %s: no applicable conversion defined' % os.path.basename(outbase)
                self.log and self.log.warning(msg) or print(msg)
        return result, main_file

    def to_img(self, outbase):
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

    def to_dti(self, outbase):
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

    def to_nii(self, outbase):
        """Create a single nifti file from an ordered list of dicoms."""
        flipped = False
        slice_loc = [dcm_i.SliceLocation for dcm_i in self.dcm_list]
        slice_num = [dcm_i.InstanceNumber for dcm_i in self.dcm_list]
        image_position = [dcm_i.ImagePositionPatient for dcm_i in self.dcm_list]
        image_data = np.dstack([np.swapaxes(dcm_i.pixel_array, 0, 1) for dcm_i in self.dcm_list])

        unique_slice_loc = np.unique(slice_loc)
        slices_per_volume = len(unique_slice_loc) # also: image[TAG_SLICES_PER_VOLUME].value
        num_volumes = self.first_dcm.ImagesinAcquisition / slices_per_volume
        dims = np.array((self.first_dcm.Rows, self.first_dcm.Columns, slices_per_volume, num_volumes))

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
                self.log and self.log.debug("dimensions indicate missing slices from volume - zero padding the gap")
                padding = np.zeros((self.first_dcm.Rows, self.first_dcm.Columns, slices_padding))
                image_data = np.dstack([image_data, padding])
            volume_start_indices = range(0, slices_total_rounded_up, slices_per_volume)
            image_data = np.concatenate([image_data[:,:,index:(index + slices_per_volume),np.newaxis] for index in volume_start_indices], axis=3)

        # Check for multi-echo data where duplicate slices might be interleaved
        # TODO: we only handle the 4d case here, but this could in theory happen with others.
        if num_volumes>1 and slice_loc[0::num_volumes]==slice_loc[1::num_volumes] and image_data.ndim==4:
            tmp = image_data.copy()
            for vol_num in range(num_volumes):
                image_data[:,:,:,vol_num] = tmp[:,:,vol_num::num_volumes,:].reshape(image_data.shape[0:3], order='F')

        mm_per_vox = np.hstack((self.first_dcm.PixelSpacing, self.first_dcm.SpacingBetweenSlices)).astype(float)

        row_cosines = self.first_dcm.ImageOrientationPatient[0:3]
        col_cosines = self.first_dcm.ImageOrientationPatient[3:6]
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
        qto_xyz[0:3,0:3] = np.dot(qto_xyz[0:3,0:3], np.diag(mm_per_vox))

        nii_header = nibabel.Nifti1Header()
        nii_header.set_xyzt_units('mm', 'sec')
        nii_header.set_qform(qto_xyz, 'scanner')
        nii_header.set_sform(qto_xyz, 'scanner')

        nii_header['slice_start'] = 0
        nii_header['slice_end'] = slices_per_volume - 1
        slice_order = SLICE_ORDER_UNKNOWN
        if slices_total >= slices_per_volume and 'TriggerTime' in self.first_dcm and self.first_dcm.TriggerTime != '':
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

        if TAG_PHASE_ENCODE_DIR in self.first_dcm and self.first_dcm[TAG_PHASE_ENCODE_DIR].value == 'ROWS':
            fps_dim = [1, 0, 2]
        else:
            fps_dim = [0, 1, 2]
        nii_header.set_dim_info(*fps_dim)

        nii_header.structarr['pixdim'][4] = float(self.first_dcm.RepetitionTime) / 1000.

        if image_data.dtype == np.dtype('int16'):
            nii_header.set_data_dtype(np.int16)

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
    dcm_series = DicomSeries(args.dcm_dir)
    dcm_series.convert(args.outbase or os.path.basename(args.dcm_dir.rstrip('/')))
