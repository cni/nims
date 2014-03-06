# @author:  Bob Dougherty
#           Gunnar Schaefer

import os
import glob
import logging
import nibabel
import dcmstack
import dcmstack.extract

import numpy as np

import nimsdata

log = logging.getLogger('nimsnifti')


class NIMSNiftiError(nimsdata.NIMSDataError):
    pass


class NIMSNifti(nimsdata.NIMSData):

    """
    A NIfTI file wrapped in a NIMS-sortable object.

    TODO: consider moving the nifti-header loading and file-writing from the NIMSImage subclasses to here.
    Then, e.g., NIMSDicom will pass the relevant metadata and the image array to NIMSNifti to write the file.
    """

    datakind = u'derived'
    datatype = u'nifti'
    filetype = u'nifti'

    def __init__(self, filepath):
        try:
            nifti = nibabel.load(filepath)
            # TODO: add metadata necessary for sorting to the NIfTI header.
            self.imagedata = nifti.get_data()
            #super(NIMSNifti, self).__init__()
        except Exception as e:
            raise NIMSNiftiError(str(e))

    @staticmethod
    def write(metadata, imagedata, outbase, notes=''):
        """Create a nifti file and possibly bval and bvec files from an ordered list of pixel data."""
        if notes != '':
            filepath = outbase + '_README.txt'
            with open(filepath, 'w') as fp:
                fp.write(notes)
            log.debug('generated %s' % os.path.basename(filepath))

        if metadata.bvals is not None and metadata.bvecs is not None:
            filepath = outbase + '.bval'
            with open(filepath, 'w') as bvals_file:
                bvals_file.write(' '.join(['%0.1f' % value for value in metadata.bvals]))
            log.debug('generated %s' % os.path.basename(filepath))
            filepath = outbase + '.bvec'
            with open(filepath, 'w') as bvecs_file:
                bvecs_file.write(' '.join(['%0.4f' % value for value in metadata.bvecs[0,:]]) + '\n')
                bvecs_file.write(' '.join(['%0.4f' % value for value in metadata.bvecs[1,:]]) + '\n')
                bvecs_file.write(' '.join(['%0.4f' % value for value in metadata.bvecs[2,:]]) + '\n')
            log.debug('generated %s' % os.path.basename(filepath))

        # Don't trust metatdata.num_slices, since the # of resulting slices might not match the # acquired.
        num_slices = imagedata.shape[2]
        nii_header = nibabel.Nifti1Header()
        nii_header.set_xyzt_units('mm', 'sec')
        nii_header.set_qform(metadata.qto_xyz, 'scanner')
        nii_header.set_sform(metadata.qto_xyz, 'scanner')
        nii_header.set_dim_info(*([1, 0, 2] if metadata.phase_encode == 0 else [0, 1, 2]))
        nii_header['slice_start'] = 0
        nii_header['slice_end'] = num_slices - 1
        nii_header['slice_duration'] = metadata.slice_duration
        nii_header['slice_code'] = metadata.slice_order
        if np.iscomplexobj(imagedata):
            clip_vals = np.percentile(np.abs(imagedata), (10.0, 99.5))
        else:
            clip_vals = np.percentile(imagedata, (10.0, 99.5))
        nii_header.structarr['cal_min'] = clip_vals[0]
        nii_header.structarr['cal_max'] = clip_vals[1]
        nii_header.structarr['pixdim'][4] = metadata.tr #FIXME cleaner way to set the TR???

        nii_header.set_data_dtype(imagedata.dtype)

        # Stuff some extra data into the description field (max of 80 chars)
        # Other unused fields: nii_header['data_type'] (10 chars), nii_header['db_name'] (18 chars),
        nii_header['descrip'] = 'te=%.2f;ti=%.0f;fa=%.0f;ec=%.4f;acq=[%s];mt=%.0f;rp=%.1f;' % (
                metadata.te * 1000.,
                metadata.ti * 1000.,
                metadata.flip_angle,
                metadata.effective_echo_spacing * 1000.,
                ','.join(map(str, metadata.acquisition_matrix)),
                metadata.mt_offset_hz,
                1. / metadata.phase_encode_undersample,
                )
        if '3D' in metadata.acquisition_type:   # for 3D acquisitions, add the slice R-factor
            nii_header['descrip'] = str(nii_header['descrip']) + 'rs=%.1f' % (1. / metadata.slice_encode_undersample)

        nifti = nibabel.Nifti1Image(imagedata, None, nii_header)
        filepath = outbase + '.nii.gz'
        nibabel.save(nifti, filepath)
        log.debug('generated %s' % os.path.basename(filepath))

        return filepath

    @staticmethod
    def write_siemens(time_order, metadata, dcm_files_path, outbase, notes=''):
        description = 'te=%.2f;ti=%.0f;fa=%.0f;ec=%.4f;acq=[%s];mt=%.0f;rp=%.1f;' % (
                metadata.te * 1000.,
                metadata.ti * 1000.,
                metadata.flip_angle,
                metadata.effective_echo_spacing * 1000.,
                ','.join(map(str, metadata.acquisition_matrix)),
                metadata.mt_offset_hz,
                1. / metadata.phase_encode_undersample,
                )
        if '3D' in metadata.acquisition_type:   # for 3D acquisitions, add the slice R-factor
            description = str(description) + 'rs=%.1f' % (1. / metadata.slice_encode_undersample)

        extractor = dcmstack.extract.MetaExtractor(ignore_rules=[dcmstack.extract.ignore_non_ascii_bytes])
        dcm_paths = glob.glob(dcm_files_path + '/*.dcm')
        stacks = dcmstack.parse_and_stack(dcm_paths, extractor=extractor, time_order=time_order,
                            group_by=('AcquisitionTime'))
        stack = stacks.values()[0]
        nifti = stack.to_nifti()
        nifti.get_header()['descrip'] = description

        filepath = outbase + '.nii.gz'
        nibabel.save(nifti, filepath)
        log.debug('generated %s' % os.path.basename(filepath))

        return filepath