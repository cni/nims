#!/usr/bin/env python
#
# @author:  Bob Dougherty
# (Note that the regressor computation code was mostly transcribed from Catie Chang's
# Matlab implementation of retroicor_rvhr.)

"""
The CNI physiological data procesor. Takes physio data (cardiac and respiration),
cleans it to be synchronous with the scan, and computes retroicor and rvhrcor regressors.
See:

* Glover GH, Li TQ, Ress D. Image-based method for retrospective correction of
  physiological motion effects in fMRI: RETROICOR. Magn Reson Med. 2000 Jul;44(1):162-7.
  PubMed PMID: 10893535

* Chang C, Cunningham JP, Glover GH. Influence of heart rate on the BOLD signal:
  the cardiac response function. Neuroimage. 2009 Feb 1;44(3):857-69. doi:
  10.1016/j.neuroimage.2008.09.029. Epub 2008 Oct 7. PubMed PMID: 18951982

"""

from __future__ import print_function

import os
import zipfile
import tarfile
import argparse
import nibabel
import numpy as np
import scipy
from scipy import signal
from scipy import stats

class PhysioDataError(Exception):
    pass

class PhysioData(object):
    """
    Read and process physiological data recorded during an MR scan.

    This class reads the physio data and generates RETROICOR and RETORVHR
    regressors from the data.

    Takes either a list of the physio files or a filename that points to a
    zip or tgz file containing the files.

    Example:
        import physio
        p = physio.PhysioData(filename='physio.zip', tr=2, nframes=120, nslices=36)
        p.generate_regressors(outname='retroicor.csv')
    """

    filetype = u'physio'

    def __init__(self, filename, tr=None, nframes=None, nslices=None, slice_order=None, log=None, card_dt=0.01, resp_dt=0.04):
        # FIXME: How to infer the file format automatically?
        self.format_str = 'ge'
        self.log = log
        self.tr = tr
        self.nframes = nframes
        if slice_order == None:
            self.nslices = nslices
            # Infer a standard GE interleave slice order
            self.slice_order = np.array(range(0, self.nslices, 2) + range(1, self.nslices, 2))
            # msg = 'No explicit slice order set; inferring interleaved.'
            # self.log and self.log.warn(msg) or print(msg)
        else:
            self.nslices = slice_order.size
            self.slice_order = np.array(slice_order)
        self.card_wave = None
        self.card_trig = None
        self.card_dt = card_dt
        self.card_time = None
        self.heart_rate = None
        self.resp_wave = None
        self.resp_trig = None
        self.resp_dt = resp_dt
        self.resp_time = None
        self.regressors = None
        self.phases = None
        self.scan_duration = self.nframes * self.tr
        if self.format_str=='ge':
            self.read_ge_data(filename)
        else:
            raise PhysioDataError('Only GE physio format is currently supported.')
            # insert other vendor's read_data functions here


    def read_ge_data(self, filename):
        # if we are passed a list, we assume it's a list of the files. Otherwise, it should be a string containing a filename.
        if getattr(filename, '__iter__', False):
            for fn in filename:
                if "RESPData" in fn:
                    self.resp_wave  = np.loadtxt(fn)
                if "RESPTrig" in fn:
                    self.resp_trig  = np.loadtxt(fn)
                if "PPGData" in fn:
                    self.card_wave = np.loadtxt(fn)
                if "PPGTrig" in fn:
                    self.card_trig = np.loadtxt(fn)
        else:
            with open(filename,'rb') as fp:
                magic = fp.read(4)
            if (magic == '\x50\x4b\x03\x04'):
                with zipfile.ZipFile(filename) as zf:
                    file_names = zf.namelist()
                    for fn in file_names:
                        if "RESPData" in fn:
                            self.resp_wave  = np.loadtxt(zf.open(fn))
                        if "RESPTrig" in fn:
                            self.resp_trig  = np.loadtxt(zf.open(fn))
                        if "PPGData" in fn:
                            self.card_wave  = np.loadtxt(zf.open(fn))
                        if "PPGTrig" in fn:
                            self.card_trig  = np.loadtxt(zf.open(fn))
            elif (magic[:2] == '\x1f\x8b'):
                with tarfile.open(filename, "r:gz") as tf:
                    file_names = tf.getnames()
                    for fn in file_names:
                        if "RESPData" in fn:
                            self.resp_wave  = np.loadtxt(tf.extractfile(tf.getmember(fn)))
                        if "RESPTrig" in fn:
                            self.resp_trig  = np.loadtxt(tf.extractfile(tf.getmember(fn)))
                        if "PPGData" in fn:
                            self.card_wave = np.loadtxt(tf.extractfile(tf.getmember(fn)))
                        if "PPGTrig" in fn:
                            self.card_trig = np.loadtxt(tf.extractfile(tf.getmember(fn)))
            else:
                raise PhysioDataError('Only tgz and zip files are supported.')

        # move time zero to correspond to the start of the fMRI data
        offset = self.resp_dt * self.resp_wave.size - self.scan_duration
        self.resp_time = self.resp_dt * np.arange(self.resp_wave.size) - offset
        resp_inds = np.nonzero(self.resp_time >= 0)[0]

        offset = self.card_dt * self.card_wave.size - self.scan_duration
        self.card_time = self.card_dt * np.arange(self.card_wave.size) - offset
        self.card_trig = self.card_trig * self.card_dt - offset
        card_inds = np.nonzero(self.card_time >= 0)[0]
        return


    def compute_regressors(self):
        """

         * catie chang,   catie.chang@nih.gov
         * bob dougherty, bobd@stanford.edu

         * 2011.12.13: original matlab implementation (catie)
         * 2012.02.14: modified from retroicor_main.m. This version
           optionally includes RVHRcor regressors too! (RV*RRF, HR*CRF,
           + time derivatives). (catie, feeling the love)
         * 2012.12.14: translated to Python (bob)

         See the following for background:
         Glover et al., 2000: MRM 44, 162-167.
         Birn et al., 2006: Neuroimage 31, 1536-1548.
         Chang et al., 2009: Neuroimage 47, 1448-1459 (appendix A)
         Chang et al., 2009: Neuroimage 44, 857-869

         ---------------------------
         INPUTS:
         ---------------------------
         * slice order:  vector indicating order of slice acquisition
             (e.g. [30 28 26, .... 29 27 ... 1] for 30 "interleaved down" slices)
         * tr: in seconds
         * nframes: number of frames in the timeseries
         * card_trig: vector of cardiac (R-wave peak) times, in seconds.
         * resp_wave: respiration amplitude signal
         * resp_dt: sampling interval between the points in respiration
             amplitude signal (in seconds, e.g. resp_dt=0.04 for 25 Hz sampling)

          (** setting card_trig = [] will ignore cardiac in both corrections)
          (** setting resp_wave = [] will ignore respiration in both corrections)


         ---------------------------
         OUTPUTS:
         ---------------------------
         * self.phases: list of cardiac & respiration phases for each slice (numpy arrays).
              phases[i,:,0] contains the cardiac phase for slice "i" and
              phases[i,:,1] contains the resp phases for slice "i".
         * self.regressors: retroicor & rvhrcor regressors as [#timepoints x #regressors x #slices].
              I.e., the regressors for slice "i" are the columns of REGRESSORS[:,:,i].
         *

        """

        t_win = 6 * 0.5 # 6-sec window for computing RV & HR, default
        nslc = self.slice_order.size

        # Find the derivative of the respiration waveform
        # shift to zero-min
        self.resp_wave = self.resp_wave - self.resp_wave.min()
        # bin respiration signal into 100 values
        Hb,bins = np.histogram(self.resp_wave, 100)
        # calculate the derivative
        # first, filter respiratory signal - just in case
        f_cutoff = 1. # max allowable freq
        fs = 1. / self.resp_dt;
        wn = f_cutoff / (fs / 2)
        ntaps = 20
        b = scipy.signal.firwin(ntaps, wn)
        respfilt = scipy.signal.filtfilt(b, [1], self.resp_wave)
        drdt = np.diff(respfilt)

        # --------------------------------------------------------------
        # find cardiac and respiratory phase vectors
        # --------------------------------------------------------------
        self.phases = np.zeros((nslc, self.nframes, 2))
        for sl in range(nslc):
            # times (for each frame) at which this slice was acquired (midpoint):
            cur_slice_acq = (sl==self.slice_order).nonzero()[0][0]
            slice_times = np.arange((self.tr/nslc)*(cur_slice_acq+0.5), self.scan_duration, self.tr)
            for fr in range(self.nframes):
                # cardiac
                prev_trigs = np.nonzero(self.card_trig < slice_times[fr])[0]
                if prev_trigs.size == 0:
                    t1 = 0.
                else:
                    t1 = self.card_trig[prev_trigs[-1]]
                next_trigs = np.nonzero(self.card_trig > slice_times[fr])[0]
                if next_trigs.size == 0:
                    t2 = self.nframes*self.tr
                else:
                    t2 = self.card_trig[next_trigs[0]]
                phi_cardiac = (slice_times[fr] - t1) * 2. * np.pi / (t2 - t1)

                # respiration: (based on amplitude histogram)
                # find the closest index in resp waveform
                iphys = np.min((np.max((0, np.round(slice_times[fr] / self.resp_dt))), drdt.size-1))
                amp = self.resp_wave[iphys]
                dbins = np.abs(amp-bins)
                thisBin = dbins.argmin()  #closest resp_wave histo bin
                numer = Hb[0:thisBin].sum().astype(float)
                phi_resp = np.pi * np.sign(drdt[iphys]) * (numer / respfilt.size)

                # store
                self.phases[sl,fr,:] = [phi_cardiac, phi_resp]

        # --------------------------------------------------------------
        # generate slice-specific retroicor regressors
        # --------------------------------------------------------------
        REGRESSORS_RET = np.zeros((self.nframes, 8, nslc))
        for sl in range(nslc):
            phi_c = self.phases[sl,:,0]
            phi_r = self.phases[sl,:,1]

            # Fourier expansion of cardiac phase
            c1_c = np.cos(phi_c)
            s1_c = np.sin(phi_c)
            c2_c = np.cos(2*phi_c)
            s2_c = np.sin(2*phi_c)

            # Fourier expansion of respiratory phase
            c1_r = np.cos(phi_r)
            s1_r = np.sin(phi_r)
            c2_r = np.cos(2*phi_r)
            s2_r = np.sin(2*phi_r)
            covs = np.array((c1_c, s1_c, c2_c, s2_c,c1_r, s1_r, c2_r, s2_r))

            REGRESSORS_RET[:,:,sl] = covs.transpose()

        # --------------------------------------------------------------
        # generate slice-specific rvhrcor regressors
        # --------------------------------------------------------------
        REGRESSORS_RVHR = np.zeros((self.nframes, 4, nslc))
        self.heart_rate = np.zeros((self.nframes, nslc))
        t = np.arange(0, 40-self.tr, self.tr) # 40-sec impulse response
        for sl in range(nslc):
            # times (for each frame) at which this slice was acquired (midpoint):
            cur_slice_acq = (sl==self.slice_order).nonzero()[0][0]
            slice_times = np.arange((self.tr/nslc)*(cur_slice_acq+0.5), self.scan_duration, self.tr)
            # make slice RV*RRF regressor
            rv = np.zeros(self.nframes)
            for tp in range(self.nframes):
                i1 = max(0, np.floor((slice_times[tp] - t_win) / self.resp_dt))
                i2 = min(self.resp_wave.size, np.floor((slice_times[tp] + t_win) / self.resp_dt))
                if i2 < i1:
                    raise PhysioDataError('Respiration data is shorter than the scan duration.')
                rv[tp] = np.std(self.resp_wave[i1:i2])

            # conv(rv, rrf)
            rv -= rv.mean()
            R = 0.6 * (t**2.1) * np.exp(-t/1.6) - 0.0023 * (t**3.54) * np.exp(-t/4.25)
            R = R / R.max()
            rv_rrf = np.convolve(rv, R)[0:rv.size]
            # time derivative
            rv_rrf_d = np.diff(rv_rrf)
            rv_rrf_d = np.concatenate(([rv_rrf_d[0]], rv_rrf_d))

            # make slice HR*CRF regressor
            hr = np.zeros(self.nframes)
            for tp in range(self.nframes):
                inds = np.nonzero(np.logical_and(self.card_trig >= (slice_times[tp]-t_win), self.card_trig <= (slice_times[tp]+t_win)))[0]
                if inds.size == 0:
                    if tp > 0:
                        # At the end of a run, the last pulse might be recorded before the last data frame.
                        hr[tp] = hr[tp-1]
                    else:
                        raise PhysioDataError('Cardiac trigger times do not match scan duration.')
                else:
                    hr[tp] = (inds[-1] - inds[0]) * 60. / (self.card_trig[inds[-1]] - self.card_trig[inds[0]])  # bpm
            # conv(hr, crf)
            self.heart_rate[:,sl] = hr
            hr -= hr.mean()
            H = 0.6 * (t**2.7) * np.exp(-t/1.6) - 16 * scipy.stats.norm.pdf(t, 12, 3)
            H /= H.max()
            hr_crf = np.convolve(hr,H)[0:hr.size]
            # time derivative
            hr_crf_d = np.diff(hr_crf)
            hr_crf_d = np.concatenate(([hr_crf_d[0]], hr_crf_d))
            REGRESSORS_RVHR[:,:,sl] = np.array((rv_rrf, rv_rrf_d, hr_crf, hr_crf_d)).transpose()

        # --------------------------------------------------------------
        # final set of physio regressors
        # --------------------------------------------------------------
        self.regressors = np.concatenate((REGRESSORS_RET, REGRESSORS_RVHR), axis=1)
        for sl in range(nslc):
            x = np.arange(self.regressors.shape[0]).transpose()
            for reg in range(self.regressors.shape[1]):
                self.regressors[:,reg,sl] -= np.polyval(np.polyfit(x, self.regressors[:,reg,sl], 2), x)

        return


    def denoise_image(self, regressors):
        """
        correct the image data: slice-wise
        FIXME: NOT TESTED
        """
        PCT_VAR_REDUCED = zeros(npix_x,npix_y,nslc)
        nslc = d.shape[2]
        self.nframes = d.shape[3]
        npix_x = d.shape[0]
        npix_y = d.shape[1]
        d_corrected = np.zeros(d.shape)
        for jj in range(nslc):
            slice_data = np.squeeze(d[:,:,jj,:])
            Y_slice = slice_data.reshape((npix_x*npix_y, self.nframes)).transpose() #ntime x nvox
            t = np.arange(self.nframes).transpose()
            # design matrix
            XX = np.array((t, t**2., REGRESSORS[:,:,jj]))
            XX = np.concatenate((np.ones((XX.shape[0],1)), np.zscore(XX)))
            Betas = np.pinv(XX) * Y_slice
            Y_slice_corr = Y_slice - XX[:,3:-1] * Betas[3:-1,:] # keep
            # calculate percent variance reduction
            var_reduced = (np.var(Y_slice,0,1) - np.var(Y_slice_corr,0,1)) / np.var(Y_slice,0,1)
            PCT_VAR_REDUCED[:,:,jj] = var_reduced.transpose().reshape((npix_x, npix_y))
            # fill corrected volume
            V_slice_corr = Y_slice_corr.transpose()
            for ii in range(self.nframes):
                d_corrected[:,:,jj,ii] = V_slice_corr[:,ii].reshape((npix_x,npix_y))

        return d_corrected, PCT_VAR_REDUCED

    def write_regressors(self, filename):
        # FIXME: write out a more portable format. Maybe a simple 2-d csv, with time running
        # down each row and column headings indicating the regressor and slice #.
        self.compute_regressors()
        # Write the array to disk
        # Thanks to Joe Kington on StackOverflow (http://stackoverflow.com/questions/3685265/how-to-write-a-multidimensional-array-to-a-text-file)
        with file(filename, 'w') as outfile:
            # Write a little header behind comments
            # Any line starting with "#" will be ignored by numpy.loadtxt
            outfile.write('# slice_order = [ ' + ','.join([str(d) for d in self.slice_order]) + ' ]\n')
            outfile.write('# Full array shape: {0}\n'.format(self.regressors.shape))
            outfile.write('# time x regressor for each slice in the acquired volume\n')
            outfile.write('# regressors: [c1_c, s1_c, c2_c, s2_c,c1_r, s1_r, c2_r, s2_r, rv_rrf, rv_rrf_d, hr_crf, hr_crf_d]\n')
            for i in range(self.regressors.shape[2]):
                outfile.write('# slice %d\n' % i)
                # Format as left-justified columns 7 chars wide with 2 decimal places.
                np.savetxt(outfile, self.regressors[:,:,i], fmt='%-7.6f')

    def is_valid(self):
        # FIXME: make these heuristics more explicit, maybe in the constructor?
        # Heuristics to detect invalid data
        # When not connected, the PPG output is very low amplitude noise
        card_valid = self.card_wave.std() > 4.
        # The respiration signal is heavily low-pass filtered, so it might look valid
        # even when it isn't connected. But the mean signal will be high if the bellows
        # are not expanded at all.
        resp_valid = self.resp_wave.mean() < 2200.
        return card_valid or resp_valid


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """ Processes physio data to make them amenable to retroicor."""
        self.add_argument('physio_file', help='path to physio data')
        self.add_argument('outbase', help='basename for output files')
        self.add_argument('-n', '--nifti_file', help='path to corresponding nifti file')
        # TODO: allow tr, nframes, and nslices to be entered as args if no nifti is provided
        # TODO: allow user to specify custom slice orders
        self.add_argument('-p', '--preprocess', action='store_true', help='Also save pre-processed physio data')


if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    ni = nibabel.load(args.nifti_file)
    tr = ni.get_header().get_zooms()[3]
    nslices = ni.shape[2]
    nframes = ni.shape[3]
    phys = PhysioData(args.physio_file, tr, nframes, nslices)
    if args.preprocess:
        np.savetxt(args.outbase + '_resp.txt', phys.resp_wave)
        np.savetxt(args.outbase + '_pulse.txt', phys.card_trig)
        np.savetxt(args.outbase + '_slice.txt', phys.slice_order)
    phys.write_regressors(args.outbase + '_reg.txt')

