#!/usr/bin/env python
#
# @author:  Bob Dougherty
#

import nibabel
import numpy as np
from dipy.segment.mask import median_otsu

class CNIDespiker(object):

    def __init__(self, spike_thresh=3, nskip=6, kspace=True):
        self.nskip = nskip
        self.spike_thresh = spike_thresh
        self.kspace = kspace

    def load_data(self, infile):
        ni = nibabel.load(infile)
        data = ni.get_data()
        trs = ni.get_header().get_zooms()[3]
        return data, trs, ni.get_affine(), ni.get_header()

    def get_masked(self, d, raw_d=None):
        mn = d[:,:,:,self.nskip:].mean(3)
        masked_data, mask = median_otsu(mn, 3, 2)
        mask = np.concatenate((np.tile(True, (d.shape[0], d.shape[1], d.shape[2], self.nskip)),
                               np.tile(np.expand_dims(mask==False, 3), (1,1,1,d.shape[3]-self.nskip))),
                               axis=3)
        # Some runs have corrupt volumes at the end (e.g., mux scans that are stopped prematurely). Mask those too.
        # But... motion correction might have interpolated the empty slices such that they aren't exactly zero.
        # So use the raw data to find these bad volumes.
        if raw_d!=None:
            slice_max = raw_d.max(0).max(0)
        else:
            slice_max = d.max(0).max(0)
        bad = np.any(slice_max==0, axis=0)
        # We don't want to miss a bad volume somewhere in the middle, as that could be a valid artifact.
        # So, only mask bad vols that are contiguous to the end.
        mask_vols = np.array([np.all(bad[i:]) for i in range(bad.shape[0])])
        # Mask out the skip volumes at the beginning
        mask_vols[0:self.nskip] = True
        mask[:,:,:,mask_vols] = True
        good_vols = np.logical_not(mask_vols)
        data_masked = np.ma.masked_array(d, mask=mask)
        return data_masked

    def spike_detect(self, d):
        c = np.vstack((np.linspace(0,1,d.shape[0]), np.linspace(1,0,d.shape[0]), np.ones((1,d.shape[0])))).T
        d_ma = self.get_masked(d)

        slice_mean = d_ma.mean(axis=0).mean(axis=0)
        t_z = (slice_mean - np.atleast_2d(slice_mean.mean(axis=1)).T) / np.atleast_2d(slice_mean.std(axis=1)).T
        spikes = t_z<-self.spike_thresh
        spike_inds = np.transpose((np.abs(t_z)>self.spike_thresh).nonzero())

        # mask out the spikes and recompute
        d_ma.mask[:,:,spike_inds[:,0],spike_inds[:,1]] = True
        slice_mean2 = d_ma.mean(axis=0).mean(axis=0)
        t_z = (slice_mean - np.atleast_2d(slice_mean2.mean(axis=1)).T) / np.atleast_2d(slice_mean2.std(axis=1)).T
        spikes = np.logical_or(spikes, t_z<-self.spike_thresh)
        spike_inds = np.transpose(spikes.nonzero())

        d_ma.mask[:,:,spike_inds[:,0],spike_inds[:,1]] = True
        slice_mean2 = d_ma.mean(axis=0).mean(axis=0)
        t_z = (slice_mean - np.atleast_2d(slice_mean2.mean(axis=1)).T) / np.atleast_2d(slice_mean2.std(axis=1)).T
        spikes = np.logical_or(spikes, t_z<-self.spike_thresh)
        spike_inds = np.transpose(spikes.nonzero())

        sl_num = np.tile(range(d.shape[2]), (d.shape[3],1)).T
        print "%d spikes detected in %d slices" % (spike_inds.shape[0], np.unique(sl_num[spike_inds[:,0]]).shape[0])
        return spike_inds, t_z


    def replace(self, d, trs):
        spike_inds, t_z = self.spike_detect(d)

        # Go back to the non-detrended data and remove the spikes by interpolating over time
        print "Repairing bad slices..."
        slices = np.unique(spike_inds[:,0])
        d_fix = d.copy()
        for z in slices:
            # Figure out which timepoints to use for the interpolation.
            # We'll usually choose the two adjacent time points, unless
            # one of those is also bad. In that case, we move out in time
            # to find the next good timepoint.
            tp_inds = spike_inds[spike_inds[:,0]==z, 1]
            tp = np.zeros(d.shape[3])
            tp[tp_inds] = 1
            left = tp + np.roll(np.hstack((tp,np.zeros(1))),1)[:-1:]
            right = tp + np.roll(np.hstack((np.zeros(1),tp)),-2)[:-1:]
            # left [right] tells us how many time points to seek to the left [right] to find good data...
            for t in tp_inds:
                print "(z,t)=(%d,%d), t_z=%f, d=%f" % (z, t, t_z[z,t], d[:,:,z,t].mean())
                if t+right[t]>=d.shape[3]:
                    d_fix[:,:,z,t] = d[:,:,z,t-left[t]]
                elif t-left[t]<0:
                    d_fix[:,:,z,t] = d[:,:,z,t+right[t]]
                else:
                    dist = np.sqrt((-left[t] - right[t])**2)
                    scale = (dist - 1.) / dist
                    if self.kspace:
                        k_fixme = np.fft.fftshift(np.fft.fft2(d[:,:,z,t]))
                        k_left = np.fft.fftshift(np.fft.fft2(d[:,:,z,t-left[t]]))
                        k_right = np.fft.fftshift(np.fft.fft2(d[:,:,z,t+right[t]]))
                        k_replace = scale * k_left + (1.-scale) * k_right
                        # indices of voxels to replace-- pixels where fix is more than thresh lower
                        diff = np.abs(k_replace) - np.abs(k_fixme)
                        thresh = np.percentile(diff,95)
                        replace_inds = diff > thresh
                        k_fixme[replace_inds] = k_replace[replace_inds]
                        d_fix[:,:,z,t] = np.abs(np.fft.ifft2(np.fft.fftshift(k_fixme)))
                        print "  replaced %d pixels in slice %d at time point %d." % (np.count_nonzero(replace_inds),z,t)
                    else:
                        d_fix[:,:,z,t] = scale * d[:,:,z,t-left[t]] + (1.-scale) * d[:,:,z,t+right[t]]
                        print "  replaced slice %d at time point %d." % (z,t)

        return d_fix


if __name__ == "__main__":
    import argparse
    import os
    import sys

    arg_parser = argparse.ArgumentParser()
    arg_parser.description = """Run the CNI despiker algorithm on a nifti file."""
    arg_parser.add_argument('infile', help='path to NIfTI file to despike')
    arg_parser.add_argument('outfile', nargs='?', help='path to output file (default=input_file_despiked.nii.gz)')
    arg_parser.add_argument('-t', '--spike_thresh', type=float, default=3., metavar='[3.0]', help='z-score threshold for spike detector.')
    arg_parser.add_argument('-n', '--nskip', type=int, default=6, metavar='[6]', help='number of timepoints at the beginning to ignore.')
    arg_parser.add_argument('-k', '--kspace', default=False, action='store_true', help='fix data in k-space (default is image space)')
    args = arg_parser.parse_args()
    if not args.outfile:
        fn,ext1 = os.path.splitext(args.infile)
        fn,ext0 = os.path.splitext(fn)
        outfile = fn + '_despiked' + ext0 + ext1
    else:
        outfile = args.outfile

    if os.path.exists(outfile):
        print('Output file "' + outfile + '" exists. Exiting...')
        sys.exit(1)

    despiker = CNIDespiker(args.spike_thresh, args.nskip, args.kspace)
    print '--------------------------------------------------------------'
    print 'Despiking:' + args.infile
    print 'Loading data...'
    data, trs, affine, header = despiker.load_data(args.infile)
    print 'Repairing spikes...'
    data_fixed = despiker.replace(data, trs)
    print 'Writing new nifti to ' + args.outfile
    nii_new = nibabel.nifti1.Nifti1Image(data_fixed, affine, header)
    nii_new.to_filename(outfile)


