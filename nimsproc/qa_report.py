#!/usr/bin/env python
#
# @author:  Bob Dougherty
#

import transaction
import sqlalchemy
from nimsgears.model import *
import nibabel as nb
import os
import numpy as np
from glob import glob
from scipy.interpolate import UnivariateSpline
import nipy.algorithms.registration
from dipy.segment.mask import median_otsu
import sys
import json
import argparse
import time
import shutil
import multiprocessing

def mask(d, raw_d=None, nskip=3):
    mn = d[:,:,:,nskip:].mean(3)
    masked_data, mask = median_otsu(mn, 3, 2)
    mask = np.concatenate((np.tile(True, (d.shape[0], d.shape[1], d.shape[2], nskip)),
                           np.tile(np.expand_dims(mask==False, 3), (1,1,1,d.shape[3]-nskip))),
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
    mask_vols[0:nskip] = True
    mask[:,:,:,mask_vols] = True
    brain = np.ma.masked_array(d, mask=mask)
    good_vols = np.logical_not(mask_vols)
    return brain,good_vols

def find_spikes(d, spike_thresh):
    slice_mean = d.mean(axis=0).mean(axis=0)
    t_z = (slice_mean - np.atleast_2d(slice_mean.mean(axis=1)).T) / np.atleast_2d(slice_mean.std(axis=1)).T
    spikes = np.abs(t_z)>spike_thresh
    spike_inds = np.transpose(spikes.nonzero())
    # mask out the spikes and recompute z-scores using variance uncontaminated with spikes.
    # This will catch smaller spikes that may have been swamped by big ones.
    d.mask[:,:,spike_inds[:,0],spike_inds[:,1]] = True
    slice_mean2 = d.mean(axis=0).mean(axis=0)
    t_z = (slice_mean - np.atleast_2d(slice_mean.mean(axis=1)).T) / np.atleast_2d(slice_mean2.std(axis=1)).T
    spikes = np.logical_or(spikes, t_z<-spike_thresh)
    spike_inds = np.transpose(spikes.nonzero())
    return((spike_inds, t_z))

def plot_slices(t_z, spike_thresh):
    import matplotlib.pyplot as plt
    c = np.vstack((np.linspace(0,1.,t_z.shape[0]), np.linspace(1,0,t_z.shape[0]), np.ones((2,t_z.shape[0])))).T
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

def estimate_motion(nifti_image):
    # BEGIN STDOUT SUPRESSION
    actualstdout = sys.stdout
    sys.stdout = open(os.devnull,'w')
    # We want to use the middle time point as the reference. But the algorithm does't allow that, so fake it.
    ref_vol = nifti_image.shape[3]/2 + 1
    ims = nb.four_to_three(nifti_image)
    ims[0] = ims[ref_vol]
    reg = nipy.algorithms.registration.FmriRealign4d(nb.concat_images(ims), 'ascending', time_interp=False)
    reg.estimate(loops=3) # default: loops=5
    aligned = reg.resample(0)
    sys.stdout = actualstdout
    # END STDOUT SUPRESSION
    mean_disp = []
    transrot = []
    for T in reg._transforms[0]:
        # get the full affine for this volume by pre-multiplying by the reference affine
        #mc_affine = np.dot(ni.get_affine(), T.as_affine())
        transrot.append(T.translation.tolist()+T.rotation.tolist())
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
    return aligned,np.array(mean_disp),np.array(transrot)

def generate_qa_report(epoch_id, nimspath, force=False, spike_thresh=6., nskip=6):
    # Note: the caller may have locked the db, so we should be sure to commit the transaction asap.
    start_secs = time.time()
    epoch = Epoch.get(epoch_id)
    if force or epoch.qa_status==u'pending' or epoch.qa_status==u'rerun':
        epoch.qa_status = u'running'
        transaction.commit()
        DBSession.add(epoch)
    else:
        if epoch.qa_status==u'running':
            print('%s epoch id %d (%s) QA: appears to be running; aborting.' % (time.asctime(), epoch_id, str(epoch)))
        else:
            print('%s epoch id %d (%s) QA: appears to be done already; aborting. Use "--force" to redo it.' % (time.asctime(), epoch_id, str(epoch)))
        transaction.commit()
        return

    print('%s epoch id %d (%s) QA: Starting QA report...' % (time.asctime(), epoch_id, str(epoch)))
    qa_ds = [ds for ds in epoch.datasets if ds.filetype==u'json' and ds.label==u'QA']
    if len(qa_ds)>0:
        if force:
            for ds in qa_ds:
                if os.path.isdir(os.path.join(nimspath, ds.relpath)):
                    shutil.rmtree(os.path.join(nimspath, ds.relpath))
                ds.delete()
    ni_ds = [ds for ds in epoch.datasets if ds.filetype==u'nifti']
    if len(ni_ds)<1:
        # Keep it pending, since the nifti might be being generated.
        print("%s epoch id %d (%s) QA: Epoch has no nifti; aborting." % (time.asctime(), epoch_id, str(epoch)))
        epoch.qa_status = u'pending'
    else:
        ni_fname = os.path.join(nimspath, ni_ds[0].relpath, ni_ds[0].filenames[0])
        ni = nb.load(ni_fname)
        tr = ni.get_header().get_zooms()[3]
        dims = ni.get_shape()
        if len(dims)<4 or dims[3]<nskip+3:
            print("%s epoch id %d (%s) QA: not enough timepoints in nifti; aborting." % (time.asctime(), epoch_id, str(epoch)))
            epoch.qa_status = u'abandoned'
        else:
            print("%s epoch id %d (%s) QA: finding spikes..." % (time.asctime(), epoch_id, str(epoch)))
            brain,good_vols = mask(ni.get_data(), nskip=nskip)
            t = np.arange(0.,brain.shape[3]) * tr
            # Get the global mean signal and subtract it out for spike detection
            global_ts = brain.mean(0).mean(0).mean(0)
            # Simple z-score-based spike detection
            spike_inds,t_z = find_spikes(brain - global_ts, spike_thresh)

            # Compute temporal snr on motion-corrected data,
            print("%s epoch id %d (%s) QA: estimating motion..." % (time.asctime(), epoch_id, str(epoch)))
            aligned,mean_disp,transrot = estimate_motion(ni)
            brain_aligned = np.ma.masked_array(aligned.get_data(), brain.mask)
            # Remove slow-drift (3rd-order polynomial) from the variance
            global_ts_aligned = brain_aligned.mean(0).mean(0).mean(0)
            global_trend = np.poly1d(np.polyfit(t[good_vols], global_ts_aligned[good_vols], 3))(t)
            tsnr = brain_aligned.mean(axis=3) / (brain_aligned - global_trend).std(axis=3)
            median_tsnr = np.ma.median(tsnr)
            # convert rotations to degrees
            transrot[:,3:] *= 180./np.pi
            qa_ds = Dataset.at_path(nimspath, u'json')
            qa_ds.filenames = [u'qa_report.json']
            qa_ds.container = epoch
            outfile = os.path.join(nimspath, qa_ds.relpath, qa_ds.filenames[0])
            print("%s epoch id %d (%s) QA: writing report to %s..." % (time.asctime(), epoch_id, str(epoch), outfile))
            with open(outfile, 'w') as fp:
                json.dump([{'dataset': ni_fname, 'tr': tr.tolist(),
                            'frame #': range(0,brain.shape[3]),
                            'transrot': transrot.round(3).tolist(),
                            'mean displacement': mean_disp.round(3).tolist(),
                            'max md': mean_disp.max().round(3).astype(float),
                            'median md': np.median(mean_disp).round(3).astype(float),
                            'temporal SNR (median)': median_tsnr.round(3).astype(float),
                            'global mean signal': global_ts.round(2).tolist(fill_value=global_ts.mean()),
                            'timeseries zscore': t_z.round(3).tolist(fill_value=0),
                            'spikes': spike_inds.tolist()}],
                          fp)
        # the state may have changed while we were processing...
        if epoch.qa_status!=u'rerun':
            epoch.qa_status = u'done'
    print("%s epoch id %d (%s) QA: Finished in %0.2f minutes." % (time.asctime(), epoch_id, str(epoch), (time.time()-start_secs)/60.))
    transaction.commit()
    return

def run_a_job(nims_path, scan_type, spike_thresh, nskip):
    # Get the latest functional epoch without qa and try it. (.desc() means descending order)
    # We need to lock the column so that another process doesn't pick this one up before we have a chance to
    # commit the transaction that marks it as 'running'.
    epoch = (Epoch.query.join(Dataset)
                        .filter((Epoch.qa_status==u'pending') | (Epoch.qa_status==u'rerun'))
                        .filter(Epoch.scan_type==scan_type)
                        .filter(Dataset.filetype==u'nifti')
                        .order_by(Epoch.timestamp.desc())
                        .with_lockmode('update')
                        .first())
    # Set force=True here so that any old QA files will be cleaned up. We've already filtered by
    # qs_status. Force a rerun of the qa by simply resetting the qa_status flag to 'rerun'.
    generate_qa_report(epoch.id, nims_path, force=True, spike_thresh=spike_thresh, nskip=nskip)


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Run CNI quality assurance metrics and save the qa report in the NIMS database."""
        self.add_argument('db_uri', metavar='URI', help='NIMS database URI')
        self.add_argument('nims_path', metavar='DATA_PATH', help='NIMS data location (must be writable)')
        self.add_argument('-f', '--force', default=False, action='store_true', help='force qa to run even it exists.')
        self.add_argument('-s', '--session_id', type=int, help='To run QA metrics on all epochs in a session, pass the session id (here) or exam # (below).')
        self.add_argument('-x', '--exam_num', type=int, help='To run QA metrics on all epochs in a session, pass the exam # (here) or session id (above).')
        self.add_argument('-e', '--epoch_id', type=int, help='Run QA metrics on just this epoch.')
        self.add_argument('-t', '--spike_thresh', type=float, default=6., metavar='[6.0]', help='z-score threshold for spike detector.')
        self.add_argument('-n', '--nskip', type=int, default=6, metavar='[6]', help='number of initial timepoints to skip.')
        self.add_argument('-j', '--jobs', type=int, default=4, metavar='[4]', help='Number of jobs to run in parallel.')

if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    init_model(sqlalchemy.create_engine(args.db_uri))
    scan_type = u'functional'
    if args.epoch_id:
        epochs = [args.epoch_id]
        generate_qa_report(args.epoch_id, args.nims_path, force=args.force, spike_thresh=args.spike_thresh, nskip=args.nskip)
    elif args.session_id or args.exam_num:
        if args.session_id:
            s = Session.get(args.session_id)
        else:
            s = Session.query.filter(Session.exam==args.exam_num).first()
        epoch_ids = [e.id for e in s.epochs if e.scan_type==scan_type]
        for eid in epoch_ids:
            generate_qa_report(eid, args.nims_path, force=args.force, spike_thresh=args.spike_thresh, nskip=args.nskip)
    else:
        # Run continuously, doing QA on the latest epoch without QA.
        while True:
            if args.jobs==1:
                run_a_job(args.nims_path, spike_thresh=args.spike_thresh, nskip=args.nskip)
            else:
                if len(multiprocessing.active_children())<args.jobs:
                    t = multiprocessing.Process(target=run_a_job, args=(args.nims_path, scan_type, args.spike_thresh, args.nskip))
                    t.start()
                time.sleep(1)


