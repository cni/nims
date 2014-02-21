#!/usr/bin/env python

import transaction
import sqlalchemy
from nimsgears.model import *
import nibabel as nb
import os
import numpy as np
from glob import glob
from scipy.interpolate import UnivariateSpline
import nipy.algorithms.registration
import sys
import json
import argparse
import time
import shutil

def mask(d, nskip=6):
    mn = d[:,:,:,nskip:].mean(3)
    clip_vals = np.percentile(mn, (40.0, 95.0))
    mask = np.concatenate((np.tile(True, (d.shape[0], d.shape[1], d.shape[2], nskip)),
                           np.tile(np.expand_dims((mn>clip_vals[0])==False, 3), (1,1,1,d.shape[3]-nskip))),
                           axis=3)
    brain = np.ma.masked_array(d, mask=mask, copy=True)
    mask[:,:,:,0:nskip] = False
    back = np.ma.masked_array(d, mask=np.logical_or(mask==False, d<1.), copy=True)
    return brain,back

def find_spikes(d, spike_thresh=3):
    slice_mean = d.mean(axis=0).mean(axis=0)
    t_z = (slice_mean - np.atleast_2d(slice_mean.mean(axis=1)).T) / np.atleast_2d(slice_mean.std(axis=1)).T
    spikes = np.abs(t_z)>spike_thresh
    spike_inds = np.transpose(spikes.nonzero())

    # mask out the spikes and recompute z-scores using variance uncontaminated with spikes.
    # This will catch smaller spikes that may have been swamped by big ones.
    d.mask[:,:,spike_inds[:,0],spike_inds[:,1]] = True
    slice_mean2 = d.mean(axis=0).mean(axis=0)
    t_z = (slice_mean - np.atleast_2d(slice_mean2.mean(axis=1)).T) / np.atleast_2d(slice_mean2.std(axis=1)).T
    spikes = np.logical_or(spikes, t_z<-spike_thresh)
    spike_inds = np.transpose(spikes.nonzero())

    d.mask[:,:,spike_inds[:,0],spike_inds[:,1]] = True
    slice_mean2 = d.mean(axis=0).mean(axis=0)
    t_z = (slice_mean - np.atleast_2d(slice_mean2.mean(axis=1)).T) / np.atleast_2d(slice_mean2.std(axis=1)).T
    spikes = np.logical_or(spikes, t_z<-spike_thresh)
    spike_inds = np.transpose(spikes.nonzero())

    return((spike_inds, t_z))

def plot_slices(t_z, spike_thresh):
    import matplotlib.pyplot as plt

    c = np.vstack((np.linspace(0,1.,d.shape[2]), np.linspace(1,0,d.shape[2]), np.ones((2,d.shape[2])))).T
    sl_num = np.tile(range(t_z.shape[0]), (t_z.shape[1], 1)).T
    print "%d spikes detected in %d slices" % (spike_inds.shape[0], np.unique(sl_num[spike_inds[:,0]]).shape[0])
    plt.figure(figsize=(16,4))
    for sl in range(t_z.shape[0]):
        plt.plot(t_z[sl,:], color=c[sl,:])
    plt.plot((0,t_z.shape[1]),(-spike_thresh,-spike_thresh),'k:')
    plt.plot((0,t_z.shape[1]),(spike_thresh,spike_thresh),'k:')
    plt.xlabel('time (frame #)')
    plt.ylabel('signal intensity (z-score)')

    from mpl_toolkits.axes_grid1 import make_axes_locatable
    divider = make_axes_locatable(plt.gca())
    cax = divider.append_axes("right", "5%", pad="3%")
    plt.imshow(np.tile(c,(2,1,1)).transpose((1,0,2)), axes=cax)
    plt.xticks([])
    plt.ylabel('Slice number')
    plt.tight_layout()

def motion_correct(nifti_image):
    # BEGIN STDOUT SUPRESSION
    actualstdout = sys.stdout
    sys.stdout = open(os.devnull,'w')
    reg = nipy.algorithms.registration.FmriRealign4d(nifti_image, 'ascending', time_interp=False)
    reg.estimate()
    aligned = reg.resample(0)
    sys.stdout = actualstdout
    # END STDOUT SUPRESSION
    mean_disp = []
    for T in reg._transforms[0]:
        # get the full affine for this volume by pre-multiplying by the reference affine
        #mc_affine = np.dot(ni.get_affine(), T.as_affine())
        # Compute the mean displacement
        # See http://www.fmrib.ox.ac.uk/analysis/techrep/tr99mj1/tr99mj1/node5.html
        T_error = T.as_affine() - np.eye(4)
        A = np.matrix(T_error[0:3,0:3])
        t = np.matrix(T_error[0:3,3]).T
        # radius of the spherical head assumption (in mm):
        R = 80.
        # The center of the volume. Assume 0,0,0 in world coordinates.
        xc = np.matrix((0,0,0)).T
        mean_disp.append(np.sqrt( R**2. / 5 * np.trace(A.T * A) + (t + A*xc).T * (t + A*xc) ).item())
    return aligned,np.array(mean_disp)

def generate_qa_report(epoch_id, nimspath, force=False):
    epoch = Epoch.get(epoch_id)
    print('Running QA on ' + str(epoch) + '...')
    qa_ds = [ds for ds in epoch.datasets if ds.filetype==u'json' and ds.label==u'QA']
    if len(qa_ds)>0:
        if force:
            for ds in qa_ds:
                shutil.rmtree(os.path.join(nimspath, ds.relpath))
                ds.delete()
            epoch.qa_status = u'pending'
        else:
            # This epoch has QA. Mark it as such.
            epoch.qa_status = u'done'
        transaction.commit()
        DBSession.add(epoch)
    if force or epoch.qa_status==None or epoch.qa_status==u'pending':
        epoch.qa_status = u'running'
        transaction.commit()
        DBSession.add(epoch)
        ni_ds = [ds for ds in epoch.datasets if ds.filetype==u'nifti'][0]
        ni_fname = os.path.join(nimspath, ni_ds.relpath, ni_ds.filenames[0])
        ni = nb.load(ni_fname)
        tr = ni.get_header().get_zooms()[3]
        dims = ni.get_shape()
        if len(dims)<4 or dims[3]<6:
            print('Not a time series-- aborting.')
        else:
            print('   Estimating motion...')
            aligned,mean_disp = motion_correct(ni)
            print('   Finding spikes...')
            brain,background = mask(aligned.get_data(), nskip=3)
            t = np.arange(0.,brain.shape[3]) * tr
            # Get the global mean signal and subtract it out
            global_ts = UnivariateSpline(t, brain.mean(0).mean(0).mean(0), s=10)
            # Simple z-score-based spike detection
            spike_inds,t_z = find_spikes(brain - global_ts(t), spike_thresh=5.)
            tsnr = brain.mean(axis=3) / brain.std(axis=3)
            median_tsnr = np.ma.median(tsnr)
            qa_ds = Dataset.at_path(nimspath, u'json')
            qa_ds.filenames = [u'qa_report.json']
            qa_ds.container = epoch
            outfile = os.path.join(nimspath, qa_ds.relpath, qa_ds.filenames[0])
            with open(outfile, 'w') as fp:
                json.dump([{'dataset': ni_fname, 'tr': tr.tolist(),
                            'frame #': range(0,brain.shape[3]),
                            'mean displacement': mean_disp.round(3).tolist(),
                            'max md': mean_disp.max().round(3).astype(float),
                            'median md': np.median(mean_disp).round(3).astype(float),
                            'temporal SNR (median)': median_tsnr.round(3).astype(float),
                            'timeseries zscore': t_z.round(3).tolist(fill_value=0),
                            'spikes': spike_inds.tolist()}],
                          fp)
        epoch.qa_status = u'done'
        transaction.commit()
        print('   Finished.')
    else:
        print('   QA appears to have already been run on this epoch. Use --force to rerun it.')


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Run CNI quality assurance metrics and save the qa report in the NIMS database."""
        self.add_argument('-f', '--force', default=False, action='store_true', help='force qa to run even it exists.')
        self.add_argument('-s', '--session_id', help='To run QA metrics on all epochs in a session, pass the session id.')
        self.add_argument('-e', '--epoch_id', help='Run QA metrics on this epoch.')
        uri = 'postgresql://nims:nims@cnifs.stanford.edu:5432/nims'
        self.add_argument('-u', '--uri', metavar='URI', default=uri, help='URI pointing to the NIMS database. (Default=%s)' % uri)
        self.add_argument('nimspath', default='/cnifs/nims/', help='path to NIMS data (must be writable)')

if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    init_model(sqlalchemy.create_engine(args.uri))
    if args.epoch_id:
        generate_qa_report(args.epoch_id, args.nimspath, force=args.force)
    elif args.session_id:
        s = Session.get(args.session_id)
        func_epoch_ids = [e.id for e in s.epochs if e.scan_type==u'functional']
        for epoch_id in func_epoch_ids:
            generate_qa_report(epoch_id, args.nimspath, force=args.force)
            #DBSession.add(s)
    else:
        # Run continuously, doing QA on the latest epoch with it.
        while True:
            time.sleep(1)

# TODO: enable the 'force' option. To do it right, we need to clean up old QA datasets.
# We might want to do that by default, since we generally never want more than one QA on an epoch.
# Also, we should put qa_status on the epoch, not the dataset.
