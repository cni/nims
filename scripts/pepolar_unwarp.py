#!/usr/bin/env python

from nipype.interfaces import fsl
import nibabel as nb
import numpy as np
import nimsdata
import shutil

# d = Dataset.get()
# d.filenames = sorted([os.path.basename(f).decode() for f in glob(os.path.join('/net/cnifs/cnifs/nims/',d.relpath,'*'))])

class UnwarpEpi(object):

    def __init__(self, out_basename, num_vols=2):
        self.b0_file = out_basename+'_b0.nii.gz'
        self.acq_file = out_basename+'_acqparams.txt'
        self.dwi_base = out_basename+'_dwi'
        self.index_file = out_basename+'_index.txt'
        self.bval_file = self.dwi_base+'.bval'
        self.bvec_file = self.dwi_base+'.bvec'
        self.topup_out = out_basename+'_topup'
        self.movpar = None
        self.fieldcoef = None
        self.b0_unwarped = None
        self.eddy_params = None
        self.eddy_out = self.dwi_base+'_ec'
        self.num_vols = num_vols

    def prep_data(self, nifti1, nifti2, bval1=None, bvec1=None, bval2=None, bvec2=None):
        ''' Load the reconstructed image files and generate the files that TOPUP needs. '''
        ni1 = nb.load(nifti1)
        ni2 = nb.load(nifti2)
        ''' Get some info from the nifti headers '''
        phase_dim1 = ni1.get_header().get_dim_info()[1]
        phase_dim2 = ni2.get_header().get_dim_info()[1]
        if int([s for s in ni1.get_header().__getitem__('descrip').tostring().split(';') if s.startswith('pe=')][0].split('=')[1][0])==1:
            pe_dir1 = 1
        else:
            pe_dir1 = -1
        if int([s for s in ni2.get_header().__getitem__('descrip').tostring().split(';') if s.startswith('pe=')][0].split('=')[1][0])==1:
            pe_dir2 = 1
        else:
            pe_dir2 = -1
        ecsp1 = float([s for s in ni1.get_header().__getitem__('descrip').tostring().split(';') if s.startswith('ec=')][0].split('=')[1])
        readout_time1 = ecsp1 * ni1.shape[phase_dim1] / 1000. # its saved in ms, but we want secs
        ecsp2 = float([s for s in ni2.get_header().__getitem__('descrip').tostring().split(';') if s.startswith('ec=')][0].split('=')[1])
        readout_time2 = ecsp2 * ni2.shape[phase_dim1] / 1000.

        if bval1!=None:
            bvals1 = np.loadtxt(bval1)
            bvals2 = np.loadtxt(bval2)
            bvecs1 = np.loadtxt(bvec1)
            bvecs2 = np.loadtxt(bvec2)
            nondwi1 = [im for i,im in enumerate(nb.four_to_three(ni1)) if bvals1[i]<10 and i<self.num_vols]
            nondwi2 = [im for i,im in enumerate(nb.four_to_three(ni2)) if bvals2[i]<10 and i<self.num_vols]
        else:
            nondwi1 = [im for i,im in enumerate(nb.four_to_three(ni1)) if i<self.num_vols]
            nondwi2 = [im for i,im in enumerate(nb.four_to_three(ni2)) if i<self.num_vols]

        b0 = nb.concat_images(nondwi1+nondwi2)
        # Topup requires an even number of slices
        if b0.shape[2]%2:
            d = b0.get_data()
            d = np.concatenate((d,np.zeros((d.shape[0],d.shape[1],1,d.shape[3]), dtype=d.dtype)),axis=2)
            b0 = nb.Nifti1Image(d, b0.get_affine())

        nb.save(b0, self.b0_file)
        with open(self.acq_file, 'w') as f:
            for i in xrange(len(nondwi1)):
                row = ['0','0','0',str(readout_time1),'\n']
                row[phase_dim1] = str(pe_dir1)
                f.write(' '.join(row))
            for i in xrange(len(nondwi2)):
                row = ['0','0','0',str(readout_time2),'\n']
                row[phase_dim2] = str(pe_dir2)
                f.write(' '.join(row))

        mux_ims1 = nb.four_to_three(ni1)[self.num_vols:]
        mux_ims2 = nb.four_to_three(ni2)[self.num_vols:]
        all_ims = nb.concat_images(mux_ims1 + mux_ims2)
        if all_ims.shape[2]%2:
            d = all_ims.get_data()
            d = np.concatenate((d,np.zeros((d.shape[0],d.shape[1],1,d.shape[3]), dtype=d.dtype)),axis=2)
            all_ims = nb.Nifti1Image(d, all_ims.get_affine())

        nb.save(all_ims, self.dwi_base+'.nii.gz')

        indices = ['1' for i in xrange(len(mux_ims1))] + [str(len(nondwi1)+1) for i in xrange(len(mux_ims2))]
        with open(self.index_file, 'w') as f:
            f.write(' '.join(indices))

        if bval1!=None:
            bvals = np.concatenate((bvals1[self.num_vols:],bvals2[self.num_vols:]), axis=0)
            bvecs = np.concatenate((bvecs1[:,self.num_vols:],bvecs2[:,self.num_vols:]), axis=1)
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
        topup.inputs.out_base = self.topup_out
        # The following doesn't seem to help. I guess topup isn't parallelized.
        #topup.inputs.environ = {'FSLPARALLEL':'condor', 'OMP_NUM_THREADS':'12'}
        res = topup.run()
        self.b0_unwarped = res.outputs.out_corrected
        self.fieldcoef = res.outputs.out_fieldcoef
        self.movpar = res.outputs.out_movpar

    def prep_ref_image(self, bet_frac=0.4):
        fsl.maths.MeanImage(in_file=self.b0_unwarped, dimension='T', out_file=self.b0_unwarped).run()
        bet = fsl.BET(in_file=self.b0_unwarped, frac=bet_frac, mask=True, no_output=True, out_file=self.b0_unwarped)
        res = bet.run()
        self.mask_file = res.outputs.mask_file

    def apply_topup(self):
        applytopup = fsl.ApplyTOPUP()
        applytopup.inputs.in_files = [ self.dwi_base+'.nii.gz' ]
        applytopup.inputs.encoding_file = self.acq_file
        applytopup.inputs.in_index = [ 1,2 ]
        applytopup.inputs.in_topup = "my_topup_results"
        # applytopup.cmdline
        res = applytopup.run()

    def run_eddy(self, num_threads=8):
        eddy = fsl.Eddy()
        eddy.inputs.in_file = self.dwi_base+'.nii.gz'
        eddy.inputs.in_mask = self.mask_file
        eddy.inputs.in_index = self.index_file
        eddy.inputs.in_acqp = self.acq_file
        eddy.inputs.in_bvec = self.bvec_file
        eddy.inputs.in_bval = self.bval_file
        # BUG IN NIPYPE; the following is expecting an 'existing file', but must be passed the topup base name for eddy to run.
        # It looks like this was fixed recently. Until we get the updated version, use this work-around:
        #eddy.inputs.in_topup = self.topup_out
        #eddy.inputs.args = '--topup='+self.topup_out
        eddy.inputs.in_topup_movpar = self.movpar
        eddy.inputs.in_topup_fieldcoef = self.fieldcoef
        eddy.inputs.out_base = self.eddy_out
        eddy.inputs.environ = {'OMP_NUM_THREADS':str(num_threads)}
        #print(eddy.cmdline)
        res = eddy.run()
        self.eddy_params = res.outputs.out_parameter

    def reorient_bvecs(self):
        ''' Reorient the bvecs based on the rotation matricies from the motion correction.'''
        eddy_params = np.loadtxt(self.eddy_params) # +'.eddy_parameters')
        rot = eddy_params[:,3:6]
        bvecs = np.loadtxt(self.bvec_file)
        for i,r in enumerate(rot):
            R =   np.matrix([[1.,0,0], [0,np.cos(r[0]),np.sin(r[0])], [0,-np.sin(r[0]),np.cos(r[0])]])
            R = R*np.matrix([[np.cos(r[1]),0,np.sin(r[1])], [0,1,0], [-np.sin(r[1]),0,np.cos(r[1])]])
            R = R*np.matrix([[np.cos(r[2]),np.sin(r[2]),0], [-np.sin(r[2]),np.cos(r[2]),0], [0,0,1]])
            R = np.linalg.inv(R)
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
    arg_parser.add_argument('nifti1', help='path to NIfTI file')
    arg_parser.add_argument('nifti2', help='path to another NIfTI file')
    arg_parser.add_argument('outbase', nargs='?', help='basename for output files (default=nifti1_nifti2_unwarped.nii.gz)')
    #arg_parser.add_argument('-a', '--average', default=False, action='store_true', help='average the two pe-polar datasets (default is to keep them separate)')
    arg_parser.add_argument('-f', '--bet_fraction', type=float, default=0.4, metavar='[0.4]', help='bet brain fraction (0-1; lower keeps more tissue)')
    arg_parser.add_argument('-n', '--num_vols', type=int, default=2, metavar='[2]', help='number of volumes to use for field-map estimation.')
    arg_parser.add_argument('-t', '--num_threads', type=int, default=8, metavar='[8]', help='number of threads to use.')
    args = arg_parser.parse_args()

    ni1 = args.nifti1
    ni2 = args.nifti2

    fn,ext1 = os.path.splitext(ni1)
    nifti_base1,ext0 = os.path.splitext(fn)
    fn,ext1 = os.path.splitext(ni2)
    nifti_base2,ext0 = os.path.splitext(fn)
    if not args.outbase:
        outbase = nifti_base2 + '_unwarped'
    else:
        outbase = args.outbase

    bval1 = nifti_base1 + '.bval'
    bval2 = nifti_base2 + '.bval'
    bvec1 = nifti_base1 + '.bvec'
    bvec2 = nifti_base2 + '.bvec'

    start_time = time()
    unwarper = UnwarpEpi(outbase, args.num_vols)
    print 'Unwarping %s and %s...' % (ni1, ni2)
    print 'Preparing data...'
    if os.path.exists(bval1):
        unwarper.prep_data(ni1, ni2, bval1, bvec1, bval2, bvec2)
    else:
        unwarper.prep_data(ni1, ni2)

    print 'Running TOPUP (SLOW)... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
    unwarper.run_topup()
    print 'Preping the reference image... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
    unwarper.prep_ref_image(args.bet_fraction)
    if os.path.exists(bval1):
        print 'Running eddy (SLOW)... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
        unwarper.run_eddy(num_threads=args.num_threads)
        print 'Reorienting the bvecs... (%0.1f minutes elapsed)' % ((time()-start_time)/60.,)
        unwarper.reorient_bvecs()
    print 'Finished in %0.1f minutes.' % ((time()-start_time)/60.,)




