# @author:  Bob Dougherty
#           Gunnar Schaefer

import os
import logging
import nibabel

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
        nifti = nibabel.load(filepath)
        # TODO: add metadata necessary for sorting to the NIfTI header.
        self.imagedata = nifti.get_data()
        self.metadata = self
        #super(NIMSNifti, self).__init__()

    @staticmethod
    def write(metadata, imagedata, outbase, notes=''):
        """Create a nifti file and possibly bval and bvec files from an ordered list of pixel data."""
        if notes != '':
            filepath = outbase + '_README.txt'
            with open(filepath, 'w') as fp:
                fp.write(notes)
            log.debug('generated %s' % os.path.basename(filepath))

        if metadata.bvals and metadata.bvecs:
            filepath = outbase + '.bval'
            with open(filepath, 'w') as bvals_file:
                bvals_file.write(' '.join(['%f' % value for value in metadata.bvals]))
            log.debug('generated %s' % os.path.basename(filepath))
            filepath = outbase + '.bvec'
            with open(filepath, 'w') as bvecs_file:
                bvecs_file.write(' '.join(['%f' % value for value in metadata.bvecs[0,:]]) + '\n')
                bvecs_file.write(' '.join(['%f' % value for value in metadata.bvecs[1,:]]) + '\n')
                bvecs_file.write(' '.join(['%f' % value for value in metadata.bvecs[2,:]]) + '\n')
            log.debug('generated %s' % os.path.basename(filepath))

        qto_xyz = np.zeros((4,4))
        qto_xyz[0,0:3] = (-metadata.row_cosines[0], -metadata.col_cosines[0], -metadata.slice_norm[0])
        qto_xyz[1,0:3] = (-metadata.row_cosines[1], -metadata.col_cosines[1], -metadata.slice_norm[1])
        qto_xyz[2,0:3] = ( metadata.row_cosines[2],  metadata.col_cosines[2],  metadata.slice_norm[2])
        qto_xyz[:,3] = np.append(metadata.image_position, 1).T
        qto_xyz[0:3,0:3] = np.dot(qto_xyz[0:3,0:3], np.diag(metadata.mm_per_vox))

        nii_header = nibabel.Nifti1Header()
        nii_header.set_xyzt_units('mm', 'sec')
        nii_header.set_qform(qto_xyz, 'scanner')
        nii_header.set_sform(qto_xyz, 'scanner')
        nii_header.set_dim_info(*([1, 0, 2] if metadata.phase_encode == 0 else [0, 1, 2]))
        nii_header['slice_start'] = 0
        nii_header['slice_end'] = metadata.num_slices - 1
        nii_header['slice_duration'] = metadata.slice_duration
        nii_header['slice_code'] = metadata.slice_order
        nii_header.structarr['cal_max'] = np.abs(imagedata).max() if np.iscomplexobj(imagedata) else imagedata.max()
        nii_header.structarr['cal_min'] = np.abs(imagedata).min() if np.iscomplexobj(imagedata) else imagedata.min()
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
