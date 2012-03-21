#!/usr/bin/env python
#
# @author:  Reno Bowen
#           Gunnar Schaefer

import os
import signal

import numpy as np

import dicom
import nibabel

import png
import nimsutil
import processor
from nimsgears import model

TAG_PHASE_ENCODE_DIR =  (0x0018, 0x1312)
TAG_PROTOCOL_DATA =     (0x0025, 0x101b)
TAG_SLICES_PER_VOLUME = (0x0021, 0x104f)
TAG_MODALITY =          (0x0008, 0x0060)
TAG_DIFFUSION_DIRS =    (0x0019, 0x10e0)
TAG_NON_DWI_IMAGES =    (0x0019, 0x10df)
TAG_BVALUE =            (0x0043, 0x1039)
TAG_BVEC =              [(0x0019, 0x10bb), (0x0019, 0x10bc), (0x0019, 0x10bd)]

SLICE_ORDER_UNKNOWN = 0
SLICE_ORDER_SEQ_INC = 1
SLICE_ORDER_SEQ_DEC = 2
SLICE_ORDER_ALT_INC = 3
SLICE_ORDER_ALT_DEC = 4
TYPE_ORIGINAL = ['ORIGINAL', 'PRIMARY', 'OTHER']
TYPE_EPI = ['ORIGINAL', 'PRIMARY', 'EPI', 'NONE']
TYPE_SCREEN = ['DERIVED', 'SECONDARY', 'SCREEN SAVE']

NIFTI_EXT = '.nii.gz'
IMAGE_EXT = '.png'
DTI_EXT = ('.bval', '.bvec')


class DicomToNifti(processor.Worker):

    taskname = u'dcm_to_nii'
    res_type = model.RawNifti

    @property
    def result_datatype(self):
        return self.res_type

    def process(self, dicom_dir, output_basepath, **kwargs):
        outfile_list = []
        dcm_list = [dicom.read_file(os.path.join(dicom_dir, f)) for f in os.listdir(dicom_dir)]
        dcm_list = sorted(dcm_list, key=lambda dcm: dcm.InstanceNumber)
        header = dcm_list[0]

        if header.ImageType == TYPE_SCREEN:
            self.res_type = model.Screensave
            for i, pixels in enumerate([dcm.pixel_array for dcm in dcm_list]):
                outfile_path = output_basepath + '_%d%s' % (i, IMAGE_EXT)
                self.dcm_to_img(pixels, outfile_path)
                outfile_list.append(outfile_path)   # FIXME: should only happen if converter was successful
        if header.ImageType == TYPE_ORIGINAL or header.ImageType == TYPE_EPI:
            outfile_path = output_basepath + NIFTI_EXT
            self.dcm_to_nii(dcm_list, outfile_path)
            outfile_list.append(outfile_path)       # FIXME: should only happen if converter was successful
        if header.ImageType == TYPE_ORIGINAL and TAG_DIFFUSION_DIRS in header and header[TAG_DIFFUSION_DIRS].value > 0:
            outfile_paths = [output_basepath+ext for ext in  DTI_EXT]
            self.dcm_to_dti(dcm_list, outfile_paths)
            outfile_list += outfile_paths           # FIXME: should only happen if converter was successful

        return (self.result_dataset(), outfile_list)

    def dcm_to_img(self, pixels, outfile_path):
        """Create a bitmap image from a dicom pixel array."""
        with open(outfile_path, 'wb') as fd:
            if pixels.ndim == 2:
                pixels = pixels.astype(np.int)
                pixels = pixels.clip(0, (pixels * (pixels != (2**15 - 1))).max())   # -32768->0; 32767->brain.max
                pixels = pixels * (2**16 -1) / pixels.max()                         # scale to full 16-bit range
                png.Writer(size=pixels.shape, greyscale=True, bitdepth=16).write(fd, pixels)
            elif pixels.ndim == 3:
                pixels = pixels.flatten().reshape((pixels.shape[1], pixels.shape[0]*pixels.shape[2]))
                png.Writer(pixels.shape[0], pixels.shape[1]/3).write(fd, pixels)

    def dcm_to_dti(self, dcm_list, outfile_paths):
        """Create bval and bvec file from a list of dicoms."""
        images_per_volume = dcm_list[0][TAG_SLICES_PER_VOLUME].value
        bvals = np.array([dcm[TAG_BVALUE].value[0] for dcm in dcm_list[0::images_per_volume]], dtype=float)
        bvecs = np.array([(dcm[TAG_BVEC[0]].value, dcm[TAG_BVEC[1]].value, dcm[TAG_BVEC[2]].value) for dcm in dcm_list[0::images_per_volume]]).transpose()
        with open(outfile_paths[0], 'w') as bvals_file:
            bvals_file.write(' '.join(['%f' % value for value in bvals]))
        with open(outfile_paths[1], 'w') as bvecs_file:
            bvecs_file.write(' '.join(['%f' % value for value in bvecs[0,:]]) + '\n')
            bvecs_file.write(' '.join(['%f' % value for value in bvecs[1,:]]) + '\n')
            bvecs_file.write(' '.join(['%f' % value for value in bvecs[2,:]]) + '\n')

    def dcm_to_nii(self, dcm_list, outfile_path):
        """Create a single nifti file from a list of dicoms."""
        first_dcm = dcm_list[0]
        flipped = False
        slice_loc = [dcm_i.SliceLocation for dcm_i in dcm_list]
        slice_num = [dcm_i.InstanceNumber for dcm_i in dcm_list]
        image_position = [dcm_i.ImagePositionPatient for dcm_i in dcm_list]
        image_data = np.dstack([np.swapaxes(dcm_i.pixel_array, 0, 1) for dcm_i in dcm_list])

        unique_slice_loc = np.unique(slice_loc)
        slices_per_volume = len(unique_slice_loc) # also: image[TAG_SLICES_PER_VOLUME].value
        num_volumes = first_dcm.ImagesinAcquisition / slices_per_volume
        dims = np.array((first_dcm.Rows, first_dcm.Columns, slices_per_volume, num_volumes))

        slices_total = len(dcm_list)
        # If we can figure the dimensions out, reshape the matrix
        if np.prod(dims) == np.size(image_data):
            image_data = image_data.reshape(dims, order='F')
        else:
            #LOG.warning("dimensions inconsistent with size, attempting to construct volume")
            # round up slices to nearest multiple of slices_per_volume
            slices_total_rounded_up = ((slices_total + slices_per_volume - 1) / slices_per_volume) * slices_per_volume
            slices_padding = slices_total_rounded_up - slices_total
            if slices_padding: #LOOK AT THIS MORE CLOSELY TODO
                #LOG.warning("dimensions indicate missing slices from volume - zero padding the gap")
                padding = np.zeros((first_dcm.Rows, first_dcm.Columns, slices_padding))
                image_data = np.dstack([image_data, padding])
            volume_start_indices = range(0, slices_total_rounded_up, slices_per_volume)
            image_data = np.concatenate([image_data[:,:,index:(index + slices_per_volume),np.newaxis] for index in volume_start_indices], axis=3)

        mm_per_vox = np.hstack((first_dcm.PixelSpacing, first_dcm.SpacingBetweenSlices))

        row_cosines = first_dcm.ImageOrientationPatient[0:3]
        col_cosines = first_dcm.ImageOrientationPatient[3:6]
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
            #LOG.info('flipping image order')
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
        if slices_total >= slices_per_volume and "TriggerTime" in first_dcm:
            first_volume = dcm_list[0:slices_per_volume]
            trigger_times = np.array([dcm_i.TriggerTime for dcm_i in first_volume])
            trigger_times_from_first_slice = trigger_times[0] - trigger_times
            nii_header['slice_duration'] = min(abs(trigger_times_from_first_slice[1:])) / 1000  # msec to sec
            if trigger_times_from_first_slice[1] < 0:
                slice_order = SLICE_ORDER_SEQ_INC if trigger_times[2] > trigger_times[1] else SLICE_ORDER_ALT_INC
            else:
                slice_order = SLICE_ORDER_ALT_DEC if trigger_times[2] > trigger_times[1] else SLICE_ORDER_SEQ_DEC
        nii_header['slice_code'] = slice_order

        if TAG_PHASE_ENCODE_DIR in first_dcm and first_dcm[TAG_PHASE_ENCODE_DIR].value == 'ROWS':
            fps_dim = [1, 0, 2]
        else:
            fps_dim = [0, 1, 2]
        nii_header.set_dim_info(*fps_dim)

        # Set the size of the voxels + TR:
        nii_header.set_zooms([float(first_dcm.PixelSpacing[0]), # str, in mm
                              float(first_dcm.PixelSpacing[0]), # str, in mm
                              float(first_dcm.SliceThickness),  # str, in mm
                        float(first_dcm.RepetitionTime)/1000.]) # str, in msec 

        
        nifti = nibabel.Nifti1Image(image_data, None, nii_header)
        nibabel.save(nifti, outfile_path)
        

if __name__ == "__main__":
    args = processor.ArgumentParser().parse_args()

    log = nimsutil.get_logger(args.logname, args.logfile, args.loglevel)

    proc = processor.Processor(args.db_uri, args.nims_path, DicomToNifti, log, args.sleeptime)

    def term_handler(signum, stack):
        proc.halt()
        log.info('Receieved SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    proc.run()
    log.warning('Process halted')
