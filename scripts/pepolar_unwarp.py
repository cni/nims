#!/usr/bin/env python

from nipype.interfaces import fsl
import nibabel as nb
import numpy as np
import nimsdata
import shutil

#in_dirs = ['/nimsfs_god/cni/huawu/20140725_1307_7515/7515_7_1_MUX3_ARC1_CAIPI_PEPolar0/','/nimsfs_god/cni/huawu/20140725_1307_7515/7515_8_1_MUX3_ARC1_CAIPI_PEPolar1/']
#in_dirs = ['/nimsfs/cni/bobd/20140811_1031_7678/7678_5_1_DTI_2mm_b1000_60dir/','/nimsfs/cni/bobd/20140811_1031_7678/7678_7_1_DTI_2mm_b1000_60dir/']
in_dirs = ['/nimsfs_god/cni/muxdwi/20140812_1306_7692/7692_4_1_DTI_2mm_pepolar0/','/nimsfs_god/cni/muxdwi/20140812_1306_7692/7692_5_1_DTI_2mm_pepolar1/']

out_basename = '/net/predator/scratch/muxdwi_recon_test/7692'

class UnwarpEpi(object):

    def __init__(self, out_basename, num_vols=2):
        self.readout_time1 = None
        self.readout_time2 = None
        self.num_cal1 = None
        self.num_cal2 = None
        self.pe_dir1 = None
        self.pe_dir2 = None
        self.b0_file = out_basename+'_b0.nii.gz'
        self.b0_unwarped = out_basename+'_b0_unwarped.nii.gz'
        self.topup_base = out_basename+'_topup'
        self.fieldmap = out_basename+'_field.nii.gz'
        self.acq_file = out_basename+'_acqparams.txt'
        self.dwi_base = out_basename+'_dwi_all'
        self.index_file = out_basename+'_index.txt'
        self.bval_file = self.dwi_base+'.bval'
        self.bvec_file = self.dwi_base+'.bvec'
        self.topup_out = out_basename+'_topup'
        self.eddy_out = self.dwi_base+'_ec'
        self.num_vols = num_vols

    def load_metadata(self, pfile1, pfile2):
        ''' Get some info from the p-file headers '''
        pf1 = nimsdata.parse(pfile1)
        pf2 = nimsdata.parse(pfile2)
        self.readout_time1 = pf1.effective_echo_spacing * pf1.size[pf1.phase_encode]
        self.readout_time2 = pf2.effective_echo_spacing * pf2.size[pf2.phase_encode]
        self.num_cal1 = pf1.num_mux_cal_cycle
        self.num_cal2 = pf2.num_mux_cal_cycle
        self.pe_dir1 = -1 if np.bitwise_and(pf1._hdr.rec.dacq_ctrl,4)==4 else 1
        self.pe_dir2 = -1 if np.bitwise_and(pf2._hdr.rec.dacq_ctrl,4)==4 else 1
        # We could get what we need from the nifti and not use the p-file, but that's risky.
        #ecsp1 = float([s for s in ni1.get_header().__getitem__('descrip').tostring().split(';') if s.startswith('ec=')][0].split('=')[1])
        #readout_time1 = ecsp1 * ni1.shape[phase_dim1]

    def prep_data(self, nifti1, bval1, bvec1, nifti2, bval2, bvec2):
        ''' Load the reconstructed image files and generate the files that TOPUP needs. '''
        ni1 = nb.load(nifti1)
        ni2 = nb.load(nifti2)
        phase_dim1 = ni1.get_header().get_dim_info()[1]
        phase_dim2 = ni2.get_header().get_dim_info()[1]

        bvals1 = np.loadtxt(bval1)
        bvals2 = np.loadtxt(bval2)
        bvecs1 = np.loadtxt(bvec1)
        bvecs2 = np.loadtxt(bvec2)

        nondwi1 = [im for i,im in enumerate(nb.four_to_three(ni1)) if bvals1[i]<10 and i<self.num_vols]
        nondwi2 = [im for i,im in enumerate(nb.four_to_three(ni2)) if bvals2[i]<10 and i<self.num_vols]

        b0 = nb.concat_images(nondwi1+nondwi2)
        # Topup requires an even number of slices
        if b0.shape[2]%2:
            d = b0.get_data()
            d = np.concatenate((d,np.zeros((d.shape[0],d.shape[1],1,d.shape[3]), dtype=d.dtype)),axis=2)
            b0 = nb.Nifti1Image(d, b0.get_affine())

        nb.save(b0, self.b0_file)
        with open(self.acq_file, 'w') as f:
            for i in xrange(len(nondwi1)):
                row = ['0','0','0',str(self.readout_time1),'\n']
                row[phase_dim1] = str(self.pe_dir1)
                f.write(' '.join(row))
            for i in xrange(len(nondwi2)):
                row = ['0','0','0',str(self.readout_time2),'\n']
                row[phase_dim2] = str(self.pe_dir2)
                f.write(' '.join(row))

        mux_ims1 = nb.four_to_three(ni1)[self.num_cal1:]
        mux_ims2 = nb.four_to_three(ni2)[self.num_cal2:]
        all_ims = nb.concat_images(mux_ims1 + mux_ims2)
        if all_ims.shape[2]%2:
            d = all_ims.get_data()
            d = np.concatenate((d,np.zeros((d.shape[0],d.shape[1],1,d.shape[3]), dtype=d.dtype)),axis=2)
            all_ims = nb.Nifti1Image(d, all_ims.get_affine())

        nb.save(all_ims, self.dwi_base+'.nii.gz')

        indices = ['1' for i in xrange(len(mux_ims1))] + [str(len(nondwi1)+1) for i in xrange(len(mux_ims2))]
        with open(self.index_file, 'w') as f:
            f.write(' '.join(indices))

        bvals = np.concatenate((bvals1[self.num_cal1:],bvals2[self.num_cal2:]), axis=0)
        bvecs = np.concatenate((bvecs1[:,self.num_cal1:],bvecs2[:,self.num_cal2:]), axis=1)
        with open(self.bval_file, 'w') as f:
            f.write(' '.join(['%0.1f' % value for value in bvals]))
        with open(self.bvec_file, 'w') as f:
            f.write(' '.join(['%0.4f' % value for value in bvecs[0,:]]) + '\n')
            f.write(' '.join(['%0.4f' % value for value in bvecs[1,:]]) + '\n')
            f.write(' '.join(['%0.4f' % value for value in bvecs[2,:]]) + '\n')

    def run_topup(self):
        topup = fsl.TOPUP()
        topup.inputs.in_file = self.b0_file
        topup.inputs.encoding_file = self.acq_file
        topup.inputs.out_corrected = self.b0_unwarped
        topup.inputs.out_field = self.fieldmap
        topup.inputs.out_base = self.topup_out
        # The following doesn't seem to help. I guess topup isn't parallelized.
        topup.inputs.environ = {'FSLPARALLEL':'condor', 'OMP_NUM_THREADS':'12'}
        res = topup.run()

    def prep_ref_image(self, bet_frac=0.4):
        fsl.maths.MeanImage(in_file=self.b0_unwarped, dimension='T', out_file=self.b0_unwarped).run()
        bet = fsl.BET(in_file=self.b0_unwarped, frac=bet_frac, mask=True, no_output=True, out_file=self.b0_unwarped)
        res = bet.run()
        self.mask_file = res.outputs.mask_file

    def run_eddy(self):
        eddy = fsl.Eddy()
        eddy.inputs.in_file = self.dwi_base+'.nii.gz'
        eddy.inputs.in_mask = self.mask_file
        eddy.inputs.in_index = self.index_file
        eddy.inputs.in_acqp = self.acq_file
        eddy.inputs.in_bvec = self.bvec_file
        eddy.inputs.in_bval = self.bval_file
        # BUG IN NIPYPE; the following is expecting an 'existing file', but must be passed the topup base name for eddy to run.
        # It looks like this was fixed recently. Until we get the updated version, use this work-around:
        #eddy.inputs.in_topup = topup_out.outputs.out_fieldcoef
        eddy.inputs.args = '--topup='+self.topup_out
        eddy.inputs.out_base = self.eddy_out
        eddy.inputs.environ = {'OMP_NUM_THREADS':'12'}
        #print(eddy.cmdline)
        res = eddy.run()

    def reorient_bvecs(self):
        ''' Reorient the bvecs based on the rotation matricies from the motion correction.'''
        eddy_params = np.loadtxt(self.eddy_out+'.eddy_parameters')
        rot = eddy_params[:,3:6]
        bvecs = np.loadtxt(self.bvec_file)
        for i,r in enumerate(rot):
            R =   np.matrix([[1.,0,0], [0,np.cos(r[0]),np.sin(r[0])], [0,-np.sin(r[0]),np.cos(r[0])]])
            R = R*np.matrix([[np.cos(r[1]),0,np.sin(r[1])], [0,1,0], [-np.sin(r[1]),0,np.cos(r[1])]])
            R = R*np.matrix([[np.cos(r[2]),np.sin(r[2]),0], [-np.sin(r[2]),np.cos(r[2]),0], [0,0,1]])
            bvecs[:,i] = (R.T * np.matrix(bvecs[:,i]).T).T
        with open(self.eddy_out+'.bvec', 'w') as fp:
            fp.write(' '.join(['%0.4f' % bv for bv in bvecs[0,:]]) + '\n')
            fp.write(' '.join(['%0.4f' % bv for bv in bvecs[1,:]]) + '\n')
            fp.write(' '.join(['%0.4f' % bv for bv in bvecs[2,:]]) + '\n')
        # also copy over the bvals
        shutil.copyfile(self.bval_file, self.eddy_out+'.bval')
        # TODO: acquire data with lots of deliberate head motion to test this

#TODO: Somewhere along the line the header geometry info is lost. Be sure to restore that in the final output files.


if __name__ == "__main__":
    import argparse
    import os
    import sys
    from time import time
    from glob import glob

    arg_parser = argparse.ArgumentParser()
    arg_parser.description = """Run FSL's TOPUP and Eddy on reconstructed EPI data. Two datasets are needed, each with a different phase-encode readout direction (i.e., one with pepolar=0, and pepolar=1)"""
    arg_parser.add_argument('nifti1', help='path to NIfTI file, or directory containing NIfTI and p-file')
    arg_parser.add_argument('nifti2', help='path to another NIfTI file, or directory containing NIfTI and p-file')
    arg_parser.add_argument('-1', '--pfile1', default=None, help='path to p-file corresponding to nifti1')
    arg_parser.add_argument('-2', '--pfile2', default=None, help='path to p-file corresponding to nifti2')
    arg_parser.add_argument('outbase', nargs='?', help='basename for output files (default=nifti1_nifti2_unwarped.nii.gz)')
    #arg_parser.add_argument('-a', '--average', default=False, action='store_true', help='average the two pe-polar datasets (default is to keep them separate)')
    arg_parser.add_argument('-f', '--bet_fraction', type=float, default=0.4, metavar='[0.4]', help='bet brain fraction (0-1; lower keeps more tissue)')
    arg_parser.add_argument('-n', '--num_vols', type=int, default=2, metavar='[2]', help='number of volumes to use for field-map estimation.')
    args = arg_parser.parse_args()

    if os.path.isdir(args.nifti1):
        ni1 = glob(os.path.join(args.nifti1,'*.nii.gz'))[0]
        pf1 = glob(os.path.join(args.nifti1,'P*.7.gz'))[0]
    else:
        ni1 = args.nifti1
        pf1 = args.pfile1

    if os.path.isdir(args.nifti2):
        ni2 = glob(os.path.join(args.nifti2,'*.nii.gz'))[0]
        pf2 = glob(os.path.join(args.nifti2,'P*.7.gz'))[0]
    else:
        ni2 = args.nifti2
        pf2 = args.pfile2

    fn,ext1 = os.path.splitext(ni1)
    nifti_base1,ext0 = os.path.splitext(fn)
    fn,ext1 = os.path.splitext(ni2)
    nifti_base2,ext0 = os.path.splitext(fn)
    if not args.outbase:
        outbase = fn + os.path.basename(nifti_base2) + '_unwarped' + ext0 + ext1
    else:
        outbase = args.outbase

    bval1 = nifti_base1 + '.bval'
    bval2 = nifti_base2 + '.bval'
    bvec1 = nifti_base1 + '.bvec'
    bvec2 = nifti_base2 + '.bvec'

    start_time = time()
    unwarper = UnwarpEpi(outbase, args.num_vols)
    print 'Unwarping %s and %s...' % (ni1, ni2)
    print 'Loading meta data...'
    unwarper.load_metadata(pf1, pf2)
    print 'Preparing data...'
    unwarper.prep_data(ni1, bval1, bvec1, ni2, bval2, bvec2)
    print 'Running TOPUP (SLOW)... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
    unwarper.run_topup()
    print 'Preping the reference image... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
    unwarper.prep_ref_image(args.bet_fraction)
    print 'Running eddy (SLOW)... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
    unwarper.run_eddy()
    print 'Reorienting the bvecs... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
    unwarper.reorient_bvecs()
    print 'Finished in %0.1f minutes.' % ((time()-start_time)/60.,)




