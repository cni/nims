#!/usr/bin/env python
#
# @author:  Bob Dougherty
#

import nibabel
import numpy as np
from scipy.interpolate import UnivariateSpline

class CNIDespiker(object):

    def __init__(self, spike_thresh=3, nskip=6):
        self.nskip = nskip
        self.spike_thresh = spike_thresh

    def load_data(self, infile):
        ni = nibabel.load(infile)
        data = ni.get_data()
        trs = ni.get_header().get_zooms()[3]
        return data, trs, ni.get_affine(), ni.get_header()

    def get_masked(self, data):
        mn = data[:,:,:,self.nskip:].mean(3)
        clip_vals = np.percentile(mn, (40.,99.))
        mask = np.concatenate((np.tile(True, (data.shape[0], data.shape[1], data.shape[2], self.nskip)),
                               np.tile(np.expand_dims((mn>clip_vals[0])==False, 3), (1,1,1,data.shape[3]-self.nskip))),
                              axis=3)
        data_masked = np.ma.masked_array(data, mask=mask)
        return data_masked

    def spike_detect(self, d):
        c = np.vstack((np.linspace(0,1,d.shape[0]), np.linspace(1,0,d.shape[0]), np.ones((1,d.shape[0])))).T
        d_ma = self.get_masked(d)

        slice_mean = d_ma.mean(axis=0).mean(axis=0)
        t_z = (slice_mean - np.atleast_2d(slice_mean.mean(axis=1)).T) / np.atleast_2d(slice_mean.std(axis=1)).T
        spikes = t_z<-self.spike_thresh
        spike_inds = np.transpose(spikes.nonzero())

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


    def replace_with_spline(self, d, trs):
        global_ts = self.get_masked(d).mean(0).mean(0).mean(0)
        t = np.arange(0.,d.shape[3]) * trs
        s = UnivariateSpline(t, global_ts, s=10)
        spike_inds, t_z = self.spike_detect(d - s(t))

        # Go back to the non-detrended data and remove the spikes by interpolating over time
        print "Replacing bad slices..."
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
            left = tp+np.roll(np.hstack((tp,np.zeros(1))),1)[:-1:]
            right = tp+np.roll(np.hstack((np.zeros(1),tp)),-2)[:-1:]
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
                    d_fix[:,:,z,t] = scale * d[:,:,z,t-left[t]] + (1.-scale) * d[:,:,z,t+right[t]]

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

    despiker = CNIDespiker(args.spike_thresh, args.nskip)
    print '--------------------------------------------------------------'
    print 'Despiking:' + args.infile
    print 'Loading data...'
    data, trs, affine, header = despiker.load_data(args.infile)
    print 'Replacing spikes according to univariate spline...'
    data_fixed = despiker.replace_with_spline(data, trs)
    print 'Writing new nifti to ' + args.outfile
    nii_new = nibabel.nifti1.Nifti1Image(data_fixed, affine, header)
    nii_new.to_filename(outfile)


