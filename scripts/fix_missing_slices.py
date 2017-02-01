import logging
import numpy as np
import nibabel as nb

log = logging.getLogger('pfile')

def load_imagedata_from_file(self, filepath):
    """
    Load raw image data from a file and do sanity checking on metadata values.

    Parameters
    ----------
    filepath : str
        path to *.mat, such as sl_001.mat

    Returns
    -------
    imagedata: np.array
        TODO: more details about np.array format?

    """
    # TODO confirm that the voxel reordering is necessary
    import scipy.io
    mat = scipy.io.loadmat(filepath)
    if 'd' in mat:
        sz = mat['d_size'].flatten().astype(int)
        slice_locs = mat['sl_loc'].flatten().astype(int) - 1
        raw = mat['d']
        raw.shape += (1,) * (4 - raw.ndim)
        if len(slice_locs)<raw.shape[2]:
            slice_locs = range(raw.shape[2])
            log.warning('Slice_locs is too short. Assuming slice_locs=[0,1,...,nslices]')
        elif sz[3] != raw.shape[3]:
            sz[3] = raw.shape[3]
            log.warning('Incorrect numer of timepoints-- fixing based on actual array size.')
        imagedata = np.zeros(sz, raw.dtype)
        imagedata[:,:,slice_locs,...] = raw[::-1,...]
    elif 'MIP_res' in mat:
        imagedata = np.atleast_3d(mat['MIP_res'])
        imagedata = imagedata.transpose((1,0,2,3))[::-1,::-1,:,:]
    if imagedata.ndim == 3:
        imagedata = imagedata.reshape(imagedata.shape + (1,))
    return imagedata

#se = '11571_5_1'
#nifti = '/nimsfs_god/hyo/benco/20160116_2014_11571/11571_6_1_BOLD_mux4_2mm_pe0/11571_6_1.nii.gz'
se = '9961_5_1'
nifti = '/nimsfs_god/hyo/benco/20150620_0948_9961/9961_6_1_BOLD_mux4_2mm_pe0/9961_6_1.nii.gz'

bn = '/predator-scratch/huawu/tmp/'+se+'_pfile/test_t0000_s'

nslices = 17
mux = 4
vol = load_imagedata_from_file(None,'%s%03d.mat' % (bn,0))

missing = []
for sl in range(1,nslices):
     try:
         vol += load_imagedata_from_file(None,'%s%03d.mat' % (bn,sl))
     except:
         print('Skipping slice %d...' % sl)
         missing.append(sl)

vol = vol[:,:,:,-1]

miss0 = [missing[0]+nslices*i for i in range(mux)]
for s in miss0:
    vol[...,s] = (vol[...,s-1]+vol[...,s+1])/2.

hd = nb.load(nifti).get_header()
ni = nb.Nifti1Image(vol, None, header=hd)
ni.update_header()
nb.save(ni, '/tmp/'+se+'.nii.gz')

