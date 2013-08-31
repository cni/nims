#!/usr/bin/env python
#
# @author:  Bob Dougherty
#           Gunnar Schaefer

from __future__ import print_function

import os
import gzip
import shlex
import shutil
import argparse
import datetime
import time
import tempfile
import subprocess as sp

import scipy.io
import numpy as np
import nibabel

import nimsutil
import pfheader


def unpack_uid(uid):
    """Convert packed PFile UID to standard DICOM UID."""
    return ''.join([str(i-1) if i < 11 else '.' for pair in [(ord(c) >> 4, ord(c) & 15) for c in uid] for i in pair if i > 0])


class PFileError(Exception):
    pass


class PFile(object):
    """
    Read pfile data and/or header.

    This class reads the data and/or header from a pfile, runs k-space reconstruction,
    and generates a NIfTI object, including header information.

    Example:
        import pfile
        pf = pfile.PFile(filename='P56832.7')
        pf.to_nii(outbase='P56832.7')
    """

    filetype = u'pfile'

    def __init__(self, filename, log=None, tmpdir=None, max_num_jobs=8, num_virtual_coils=16):
        self.filename = filename
        self.log = log
        self.max_num_jobs = max_num_jobs
        self.tmpdir = tmpdir
        self.image_data = None
        self.fm_data = None
        with open(self.filename,'rb') as fp:
            self.compressed = (fp.read(2) == '\x1f\x8b')
        self.get_metadata()
        self.basename = os.path.basename(self.filename)
        if self.basename.endswith('.gz'):
            self.basename = self.basename[:-3]
        self.filedir = os.path.dirname(self.filename)
        self.num_vcoils = num_virtual_coils

    def get_metadata(self):
        """ Get useful metadata fields from the pfile header. These should be consistent with the fields that dicomutil yields. """
        try:
            if self.compressed:
                fp = gzip.open(self.filename)
            else:
                fp = open(self.filename)
            self.header = pfheader.get_header(fp)
            fp.close()
        except (IOError, pfheader.PFHeaderError) as e:
            raise PFileError(e)
        self.exam_no = self.header.exam.ex_no
        self.series_no = self.header.series.se_no
        self.acq_no = self.header.image.scanactno
        self.exam_uid = unpack_uid(self.header.exam.study_uid)
        self.series_uid = unpack_uid(self.header.series.series_uid)
        self.series_desc = self.header.series.se_desc.strip('\x00')
        self.patient_id = self.header.exam.patidff.strip('\x00')
        self.subj_fn, self.subj_ln, self.subj_dob = nimsutil.parse_subject(
                self.header.exam.patnameff.strip('\x00'), self.header.exam.dateofbirth.strip('\x00'))
        self.psd_name = os.path.basename(self.header.image.psdname.partition('\x00')[0])
        self.physio_flag = 'sprt' in self.psd_name.lower()
        if self.header.image.im_datetime > 0:
            self.timestamp = datetime.datetime.utcfromtimestamp(self.header.image.im_datetime)
        else:   # HOShims don't have self.header.image.im_datetime
            month, day, year = map(int, self.header.rec.scan_date.strip('\x00').split('/'))
            hour, minute = map(int, self.header.rec.scan_time.strip('\x00').split(':'))
            self.timestamp = datetime.datetime(year + 1900, month, day, hour, minute) # GE's epoch begins in 1900

        self.ti = self.header.image.ti / 1e6
        self.te = self.header.image.te / 1e6
        self.tr = self.header.image.tr / 1e6  # tr in seconds
        self.flip_angle = float(self.header.image.mr_flip)
        self.pixel_bandwidth = self.header.rec.bw
        self.phase_encode = 1 if self.header.image.freq_dir == 0 else 0
        self.mt_offset_hz = self.header.image.offsetfreq

        self.num_slices = self.header.rec.nslices
        self.num_averages = self.header.image.averages
        self.num_echos = self.header.rec.nechoes
        self.receive_coil_name = self.header.image.cname.strip('\x00')
        self.num_receivers = self.header.rec.dab[0].stop_rcv - self.header.rec.dab[0].start_rcv + 1
        self.patient_id = self.header.exam.patidff.strip('\x00')
        self.operator = self.header.exam.operator_new.strip('\x00')
        self.protocol_name = self.header.series.prtcl.strip('\x00')
        self.scanner_name = self.header.exam.hospname.strip('\x00') + ' ' + self.header.exam.ex_sysid.strip('\x00')
        self.scanner_type = 'GE' # FIXME

        self.size_x = self.header.image.dim_X  # imatrix_X
        self.size_y = self.header.image.dim_Y  # imatrix_Y
        self.fov = [self.header.image.dfov, self.header.image.dfov_rect]
        self.scan_type = self.header.image.psd_iname.strip('\x00')
        self.num_bands = 1
        self.num_mux_cal_cycle = 0

        self.num_timepoints = self.header.rec.npasses
        self.deltaTE = 0.0
        self.scale_data = False

        if self.psd_name == 'sprt':
            self.num_timepoints = int(self.header.rec.user0)    # not in self.header.rec.nframes for sprt
            self.deltaTE = self.header.rec.user15
            self.band_spacing = 0
            self.scale_data = True
            # spiral is always a square encode based on the frequency encode direction (size_x)
            # Atsushi also likes to round up to the next higher power of 2.
            # self.size_x = int(pow(2,ceil(log2(pf.size_x))))
            # The rec.im_size field seems to have the correct reconned image size, but
            # this isn't guaranteed to be correct, as Atsushi's recon does whatever it
            # damn well pleases. Maybe we could add a check to infer the image size,
            # assuming it's square?
            self.size_x = self.size_y = self.header.rec.im_size
        elif self.psd_name == 'basic':
            # first 6 are ref scans, so ignore those. Also, two acquired timepoints are used
            # to generate each reconned time point.
            self.num_timepoints = (self.header.rec.npasses * self.header.rec.nechoes - 6) / 2
            self.num_echoes = 1
        elif 'mux' in self.psd_name.lower(): # multi-band EPI!
            self.num_bands = int(self.header.rec.user6)
            self.num_mux_cal_cycle = int(self.header.rec.user7)
            self.band_spacing_mm = self.header.rec.user8
            self.num_slices = self.header.image.slquant * self.num_bands
            self.num_timepoints = self.header.rec.npasses - self.num_bands*self.num_mux_cal_cycle + self.num_mux_cal_cycle
            # TODO: adjust the image.tlhc... fields to match the correct geometry.

        self.total_num_slices = self.num_slices * self.num_timepoints
        # Note: the following is true for single-shot planar acquisitions (EPI and 1-shot spiral).
        # For multishot sequences, we need to multiply by the # of shots. And for non-planar aquisitions,
        # we'd need to multiply by the # of phase encodes (accounting for any acceleration factors).
        # Even for planar sequences, this will be wrong (under-estimate) in case of cardiac-gating.
        self.prescribed_duration = datetime.timedelta(seconds=(self.num_timepoints * self.tr))
        # The actual duration can only be computed after the data are loaded. Settled for rx duration for now.
        self.duration = self.prescribed_duration
        # Compute the voxel size rather than use image.pixsize_X/Y
        self.mm_per_vox = np.array([self.fov[0] / self.size_x,
                                    self.fov[1] / self.size_y,
                                    self.header.image.slthick + self.header.image.scanspacing])

        # Compute the voxel size rather than use image.pixsize_X/Y
        self.mm_per_vox = np.array([float(self.fov[0] / self.size_x),
                                    float(self.fov[1] / self.size_y),
                                    self.header.image.slthick + self.header.image.scanspacing])
        self.effective_echo_spacing = self.header.image.effechospace / 1.e6
        self.phase_encode_undersample = 1. / self.header.rec.ileaves
        # TODO: Set this correctly! (it's in the dicom at (0x0043, 0x1083))
        self.slice_encode_undersample = 1.0
        self.acquisition_matrix = [self.size_x, self.size_y]
        # Diffusion params
        self.dwi_numdirs = self.header.rec.numdifdirs
        # You might think that the b-valuei for diffusion scans would be stored in self.header.image.b_value.
        # But alas, this is GE. Apparently, that var stores the b-value of the just the first image, which is
        # usually a non-dwi. So, we had to modify the PSD and stick the b-value into an rhuser CV. Sigh.
        self.dwi_bvalue = self.header.rec.user22
        self.diffusion_flag = True if self.dwi_numdirs >= 6 else False
        if self.diffusion_flag and self.dwi_bvalue==0:
            msg = 'the data appear to be diffusion-weighted, but image.b_value is 0!'
            self.log.warning(msg) if self.log else print(msg)

        # if bit 4 of rhtype(int16) is set, then fractional NEX (i.e., partial ky acquisition) was used.
        self.partial_ky = self.header.rec.scan_type & np.uint16(16) > 0
        self.caipi = self.header.rec.user13   # true: CAIPIRINHA-type acquisition; false: Direct aliasing of all simultaneous slices.
        self.cap_blip_start = self.header.rec.user14   # Starting index of the kz blips. 0~(mux-1) correspond to -kmax~kmax.
        self.cap_blip_inc = self.header.rec.user15   # Increment of the kz blip index for adjacent acquired ky lines.

    def set_image_data(self, data_file):
        img = self.load_image_data(data_file)
        self.update_image_data(img)

    def load_image_data(self, data_file):
        """ Load raw image data from a file and do some sanity checking on num slices, matrix size, etc. """
        # TODO: confirm that the voxel reordering is necessary. Maybe lean on the recon folks to standardize their voxel order?
        mat = scipy.io.loadmat(data_file)
        if 'd' in mat:
            sz = mat['d_size'].flatten().astype(int)
            slice_locs = mat['sl_loc'].flatten().astype(int) - 1
            img = np.zeros(sz)
            raw = np.atleast_3d(mat['d'])
            #raw = raw.transpose((3,2,1,0))[::-1,:,:,:]
            img[:,:,slice_locs,...] = raw[::-1,...]
        elif 'MIP_res' in mat:
            img = np.atleast_3d(mat['MIP_res'])
            img = img.transpose((1,0,2,3))[::-1,::-1,:,:]
        if img.ndim == 3:
            img = img.reshape(img.shape + (1,))
        return img

    def update_image_data(self, img):
        self.image_data = img
        if self.image_data.shape[0] != self.size_x or self.image_data.shape[1] != self.size_y:
            msg = 'Image matrix discrepancy. Fixing the header, assuming image_data is correct...'
            self.log.warning(msg) if self.log else print(msg)
            self.size_x = self.image_data.shape[0]
            self.size_y = self.image_data.shape[1]
            self.mm_per_vox[0] = float(self.fov[0] / self.size_x)
            self.mm_per_vox[1] = float(self.fov[1] / self.size_y)
        if self.image_data.shape[2] != self.num_slices:
            msg = 'Image slice count discrepancy. Fixing the header, assuming image_data is correct...'
            self.log.warning(msg) if self.log else print(msg)
            self.num_slices = self.image_data.shape[2]
        if self.image_data.shape[3] != self.num_timepoints:
            msg = 'Image time frame discrepancy (header=%d, array=%d). Fixing the header, assuming image_data is correct...' \
                    % (self.num_timepoints, self.image_data.shape[3])
            self.log.warning(msg) if self.log else print(msg)
            self.num_timepoints = self.image_data.shape[3]
        self.duration = self.num_timepoints * self.tr # FIXME: maybe need self.num_echoes?

    def to_nii(self, outbase, recon_executable=None, saveInOut=False):
        """Create NIFTI file from pfile."""
        if self.image_data is None:
            if self.recon_func:
                self.recon_func(recon_executable) if recon_executable else self.recon_func()
            else:
                raise PFileError('Recon not implemented for this type of data')

        if self.image_data is None: return None     # catches, for example, HO Shims

        image_tlhc = np.array([self.header.image.tlhc_R, self.header.image.tlhc_A, self.header.image.tlhc_S])
        image_trhc = np.array([self.header.image.trhc_R, self.header.image.trhc_A, self.header.image.trhc_S])
        image_brhc = np.array([self.header.image.brhc_R, self.header.image.brhc_A, self.header.image.brhc_S])
        #image_cent = np.array([self.header.image.ctr_R,  self.header.image.ctr_A,  self.header.image.ctr_S])

        row_vec = (image_trhc-image_tlhc)/np.sqrt(np.dot(image_trhc-image_tlhc, image_trhc-image_tlhc))
        col_vec = -(image_trhc-image_brhc)/np.sqrt(np.dot(image_trhc-image_brhc, image_trhc-image_brhc))
        # The DICOM standard defines these two unit vectors in an LPS coordinate frame, but we'll
        # need RAS (+x is right, +y is anterior, +z is superior) for NIFTI. So, we compute them
        # such that row_vec points to the right and col_vec points up.
        # Not sure if we need to negate the slice_norm. From the NIFTI-1 header:
        #     The third column of R will be either the cross-product of the first 2 columns or
        #     its negative. It is possible to infer the sign of the 3rd column by examining
        #     the coordinates in DICOM attribute (0020,0032) "Image Position (Patient)" for
        #     successive slices. However, this method occasionally fails for reasons that I
        #     (RW Cox) do not understand.

        # can also get slice_norm from: slice_norm = np.cross(row_vec, col_vec)
        slice_norm = np.array([self.header.image.norm_R, self.header.image.norm_A, self.header.image.norm_S])
        slice_fov = np.abs(self.header.series.start_loc - self.header.series.end_loc)

        # This is either the first slice tlhc (image_tlhc) or the last slice tlhc. How to decide?
        # And is it related to wheather I have to negate the slice_norm?
        # Tuned this empirically by comparing spiral and EPI data with the sam Rx.
        # Everything seems reasonable, except the test for axial orientation (start_ras==S|I).
        # I have no idea why I need that! But the flipping only seems necessary for axials, not
        # coronals or the few obliques I've tested.
        # FIXME: haven't tested sagittals! (to test for spiral: 'sprt' in self.psd_name.lower())
        if (self.header.series.start_ras=='S' or self.header.series.start_ras=='I') and self.header.series.start_loc > self.header.series.end_loc:
            pos = image_tlhc - slice_norm*slice_fov
            # FIXME: since we are reversing the slice order here, should we change the slice_order field below?
            self.image_data = self.image_data[:,:,::-1,]
            if self.fm_data is not None:
                self.fm_data = self.fm_data[:,:,::-1,]
        else:
            pos = image_tlhc

        if self.num_bands > 1:
            pos = pos - slice_norm * self.band_spacing_mm * (self.num_bands - 1.0) / 2.0

        qto_xyz = np.zeros((4,4))
        qto_xyz[0,0] = row_vec[0]
        qto_xyz[0,1] = col_vec[0]
        qto_xyz[0,2] = slice_norm[0]

        qto_xyz[1,0] = row_vec[1]
        qto_xyz[1,1] = col_vec[1]
        qto_xyz[1,2] = slice_norm[1]

        qto_xyz[2,0] = row_vec[2]
        qto_xyz[2,1] = col_vec[2]
        qto_xyz[2,2] = slice_norm[2]

        qto_xyz[:,3] = np.append(pos, 1).T
        qto_xyz[0:3,0:3] = np.dot(qto_xyz[0:3,0:3], np.diag(self.mm_per_vox))

        nii_header = nibabel.Nifti1Header()
        nii_header.set_xyzt_units('mm', 'sec')
        nii_header.set_qform(qto_xyz, 'scanner')
        nii_header.set_sform(qto_xyz, 'scanner')

        nii_header['slice_start'] = 0
        nii_header['slice_end'] = self.num_slices - 1
        # nifti slice order codes: 0 = unknown, 1 = sequential incrementing, 2 = seq. dec., 3 = alternating inc., 4 = alt. dec.
        slice_order = 0
        nii_header['slice_duration'] = self.tr * 1000 / self.num_slices
        # FIXME: check that this is correct.
        if   self.header.series.se_sortorder == 0:
            slice_order = 1  # or 2?
        elif self.header.series.se_sortorder == 1:
            slice_order = 3  # or 4?
        nii_header['slice_code'] = slice_order

        # Note: the freq/phase dir isn't meaningful for spiral trajectories.
        if self.header.image.freq_dir==1:
            nii_header.set_dim_info(freq=1, phase=0, slice=2)
        else:
            nii_header.set_dim_info(freq=0, phase=1, slice=2)

        # FIXME: There must be a cleaner way to set the TR! Maybe bug Matthew about it.
        nii_header.structarr['pixdim'][4] = self.tr
        nii_header.set_slice_duration(nii_header.structarr['pixdim'][4] / self.num_slices)
        nii_header.structarr['cal_max'] = self.image_data.max()
        nii_header.structarr['cal_min'] = self.image_data.min()
        # Let's stuff some extra data into the description field (max of 80 chars)
        nii_header['descrip'] = "te=%.2f;ti=%.0f;fa=%.0f;ec=%.4f;r=%.1f;acq=[%s];mt=%.0f;" % (
                                 self.te * 1000.,
                                 self.ti * 1000.,
                                 self.flip_angle,
                                 self.effective_echo_spacing * 1000.,
                                 1. / self.phase_encode_undersample,
                                 ','.join(map(str, self.acquisition_matrix)),
                                 self.mt_offset_hz)
        # Other unused fields: nii_header['data_type'] (10 chars), nii_header['db_name'] (18 chars),

        if self.num_echos == 1:
            nifti = nibabel.Nifti1Image(self.image_data, None, nii_header)
            main_file = outbase + '.nii.gz'
            nibabel.save(nifti, main_file)
        elif self.num_echos == 2:
            if saveInOut:
                nifti = nibabel.Nifti1Image(self.image_data[:,:,:,:,0], None, nii_header)
                nibabel.save(nifti, outbase + '_in.nii.gz')
                nifti = nibabel.Nifti1Image(self.image_data[:,:,:,:,1], None, nii_header)
                nibabel.save(nifti, outbase + '_out.nii.gz')
            # FIXME: Do a more robust test for spiralio!
            # Assume spiralio, so do a weighted average of the two echos.
            # FIXME: should do a quick motion correction here
            w_in = np.mean(self.image_data[:,:,:,:,0], 3)
            w_out = np.mean(self.image_data[:,:,:,:,1], 3)
            inout_sum = w_in + w_out
            w_in = w_in / inout_sum
            w_out = w_out / inout_sum
            avg = np.zeros(self.image_data.shape[0:4])
            for tp in range(self.image_data.shape[3]):
                avg[:,:,:,tp] = w_in*self.image_data[:,:,:,tp,0] + w_out*self.image_data[:,:,:,tp,1]
            nifti = nibabel.Nifti1Image(avg, None, nii_header)
            main_file = outbase + '.nii.gz'
            nibabel.save(nifti, main_file)
        else:
            main_file = None
            for echo in range(self.num_echos):
                nifti = nibabel.Nifti1Image(self.image_data[:,:,:,:,echo], None, nii_header)
                nibabel.save(nifti, outbase + '_echo%02d.nii.gz' % echo)

        if self.fm_data is not None:
            nii_header.structarr['cal_max'] = self.fm_data.max()
            nii_header.structarr['cal_min'] = self.fm_data.min()
            nifti = nibabel.Nifti1Image(self.fm_data, None, nii_header)
            nibabel.save(nifti, outbase + '_B0.nii.gz')

        if self.diffusion_flag:
            self.write_dwi_bvecs(outbase = outbase)

        return main_file

    def recon_spirec(self, executable='spirec'):
        """Do spiral image reconstruction and populate self.image_data."""
        with nimsutil.TempDirectory(dir=self.tmpdir) as tmpdir:
            if self.compressed:
                pfile_path = os.path.join(tmpdir, os.path.basename(self.filename))
                with open(pfile_path, 'wb') as fd:
                    with gzip.open(self.filename, 'rb') as gzfile:
                        fd.writelines(gzfile)
            else:
                pfile_path = os.path.abspath(self.filename)
            basepath = os.path.join(tmpdir, 'recon')
            cmd = '%s -l --rotate -90 --magfile --savefmap2 --b0navigator -r %s -t %s' % (executable, pfile_path, 'recon')
            self.log and self.log.debug(cmd)
            sp.call(shlex.split(cmd), cwd=tmpdir, stdout=open('/dev/null', 'w'))    # run spirec to generate .mag and fieldmap files

            self.image_data = np.fromfile(file=basepath+'.mag_float', dtype=np.float32).reshape([self.size_x,self.size_y,self.num_timepoints,self.num_echos,self.num_slices],order='F').transpose((0,1,4,2,3))
            if os.path.exists(basepath+'.B0freq2') and os.path.getsize(basepath+'.B0freq2')>0:
                self.fm_data = np.fromfile(file=basepath+'.B0freq2', dtype=np.float32).reshape([self.size_x,self.size_y,self.num_echos,self.num_slices],order='F').transpose((0,1,3,2))

    def recon_mux_epi(self, executable='octave', timepoints=[]):
        """Do mux_epi image reconstruction and populate self.image_data."""
        ref_file  = os.path.join(self.filedir, '_'+self.basename+'_ref.dat')
        vrgf_file = os.path.join(self.filedir, '_'+self.basename+'_vrgf.dat')
        if not os.path.isfile(ref_file) or not os.path.isfile(vrgf_file):
            raise PFileError('dat files not found')
        with nimsutil.TempDirectory(dir=self.tmpdir) as tmpdir:
            if self.compressed:
                shutil.copy(ref_file, os.path.join(tmpdir, os.path.basename(ref_file)))
                shutil.copy(vrgf_file, os.path.join(tmpdir, os.path.basename(vrgf_file)))
                pfile_path = os.path.join(tmpdir, self.basename)
                with open(pfile_path, 'wb') as fd:
                    with gzip.open(self.filename, 'rb') as gzfile:
                        fd.writelines(gzfile)
            else:
                pfile_path = os.path.abspath(self.filename)
            recon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'mux_epi_recon'))
            outname = os.path.join(tmpdir, 'sl')

            # Spawn the desired number of subprocesses until all slices have been spawned
            num_muxed_slices = self.num_slices / self.num_bands
            mux_recon_jobs = []
            slice_num = 0
            while slice_num < num_muxed_slices:
                num_running_jobs = sum([job.poll()==None for job in mux_recon_jobs])
                if num_running_jobs < self.max_num_jobs:
                    # Recon each slice separately. Note the slice_num+1 to deal with matlab's 1-indexing.
                    # Use 'str' on timepoints so that an empty array will produce '[]'
                    cmd = ('%s --no-window-system -p %s --eval \'mux_epi_main("%s", "%s_%03d.mat", [], %d, %s, %d);\''
                            % (executable, recon_path, pfile_path, outname, slice_num, slice_num+1, str(timepoints), self.num_vcoils))
                    self.log and self.log.debug(cmd)
                    mux_recon_jobs.append(sp.Popen(args=shlex.split(cmd), stdout=open('/dev/null', 'w')))
                    slice_num += 1
                else:
                    time.sleep(1.)

            # Now wait for all the jobs to finish
            for job in mux_recon_jobs:
                job.wait()

            #try:
            # Load the first slice to initialize the image array
            img = self.load_image_data("%s_%03d.mat" % (outname, 0))
            for slice_num in range(1, num_muxed_slices):
                new_img = self.load_image_data("%s_%03d.mat" % (outname, slice_num))
                # Allow for a partial last timepoint. This sometimes happens when the user aborts.
                img[...,0:new_img.shape[-1]] += new_img
            self.update_image_data(img)
            #except:
            #    raise PFileError('recon failed!')

            #sp.call(shlex.split(cmd), stdout=open('/dev/null', 'w'))
            #self.set_image_data(outname)
            # TODO: fix size_x/y,num_slices,num_timpoints if they conflict with the returned size of d.

    def write_dwi_bvecs(self, tensor_file=None, outbase=None):
        """Create bval and bvec files from a pfile."""
        if tensor_file == None:
            tensor_file = os.path.join(self.filedir, '_'+self.basename+'_tensor.dat')
        if outbase == None:
            outbase = os.path.join(self.filedir, self.basename)
        with open(tensor_file) as fp:
            uid = fp.readline().rstrip()
            ndirs = int(fp.readline().rstrip())
            bvecs = np.fromfile(fp, sep=' ')
        if uid != self.header.series.series_uid:
            self.log and self.log.debug('tensor file UID does not match PFile UID!')
            return
        if ndirs != self.dwi_numdirs or self.dwi_numdirs != bvecs.size / 3.:
            self.log and self.log.debug('tensor file numdirs does not match PFile header numdirs!')
            return

        # FIXME: Assumes that all the non-dwi images are acquired first. Getting explicit information about
        # this from the PSD would be much better!
        num_nondwi = self.num_timepoints - self.dwi_numdirs
        bvals = np.concatenate((np.zeros(num_nondwi, dtype=float), np.tile(self.dwi_bvalue, self.dwi_numdirs)))
        bvecs = np.hstack((np.zeros((3,num_nondwi), dtype=float), bvecs.reshape(self.dwi_numdirs, 3).T))
        filename = outbase + '.bval'
        with open(filename, 'w') as bvals_file:
            bvals_file.write(' '.join(['%.1f' % value for value in bvals]))
        self.log and self.log.debug('generated %s' % os.path.basename(filename))
        filename = outbase + '.bvec'
        with open(filename, 'w') as bvecs_file:
            bvecs_file.write(' '.join(['%.6f' % value for value in bvecs[0,:]]) + '\n')
            bvecs_file.write(' '.join(['%.6f' % value for value in bvecs[1,:]]) + '\n')
            bvecs_file.write(' '.join(['%.6f' % value for value in bvecs[2,:]]) + '\n')
        self.log and self.log.debug('generated %s' % os.path.basename(filename))


    def recon_hoshim(self, executable=''):
        self.log or print('Can\'t recon HO SHIM data')

    @property
    def recon_func(self):
        if self.psd_name == 'sprt':
            return self.recon_spirec
        elif 'mux' in self.psd_name:
            return self.recon_mux_epi
        elif self.psd_name == 'sprl_hos':
            return self.recon_hoshim
        else:
            return None

    @property
    def priority(self):
        return int(bool(self.recon_func)) * 2 - 1

    def get_data(self, slices=None, passes=None, coils=None, echos=None, frames=None):
        """
        Reads and returns a chunck of data from the p-file. Specify the slices,
        timepoints, coils, and echos that you want. None means you get all of
        them. The default of all Nones will return all data.
        (based on https://github.com/cni/MRS/blob/master/MRS/files.py)
        """

        n_frames = self.header.rec.nframes + self.header.rec.hnover
        n_echoes = self.header.rec.nechoes
        n_slices = self.header.rec.nslices / self.header.rec.npasses
        n_coils = self.num_receivers
        n_passes = self.header.rec.npasses
        frame_sz = self.header.rec.frame_size

        if passes == None: passes = range(n_passes)
        if coils == None: coils = range(n_coils)
        if slices == None: slices = range(n_slices)
        if echos == None: echos = range(n_echoes)
        if frames == None: frames = range(n_frames)

        # Size (in bytes) of each sample:
        ptsize = self.header.rec.point_size
        data_type = [np.int16, np.int32][ptsize/2 - 1]

        # This is double the size as above, because the data is complex:
        frame_bytes = 2 * ptsize * frame_sz

        echosz = frame_bytes * (1 + n_frames)
        slicesz = echosz * n_echoes
        coilsz = slicesz * n_slices
        passsz = coilsz * n_coils

        # Byte-offset to get to the data:
        offset = self.header.rec.off_data
        try:
            if self.compressed:
                fp = gzip.open(self.filename)
            else:
                fp = open(self.filename)
            data = np.zeros((frame_sz, len(frames), len(echos), len(slices),
                             len(coils), len(passes)), dtype=np.complex)
            for pi,passidx in enumerate(passes):
                for ci,coilidx in enumerate(coils):
                    for si,sliceidx in enumerate(slices):
                        for ei,echoidx in enumerate(echos):
                            for fi,frameidx in enumerate(frames):
                                fp.seek(passidx*passsz + coilidx*coilsz +
                                        sliceidx*slicesz + echoidx*echosz +
                                        (frameidx+1)*frame_bytes + offset)
                                dr = np.fromfile(fp, data_type, frame_sz * 2)
                                dr = np.reshape(dr, (-1, 2)).T
                                data[:, fi, ei, si, ci, pi] = dr[0] + dr[1]*1j

            fp.close()
        except (IOError, pfheader.PFHeaderError):
            raise PFileError
        return data


class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        super(ArgumentParser, self).__init__()
        self.description = """Recons a GE PFile to produce a NIfTI file and (if appropriate) a B0 fieldmap.
                              Can also take the image data in a .mat file, in which case no recon will be attempted
                              and the PFile is just used to get the necessary header information."""
        self.add_argument('pfile', help='path to pfile')
        self.add_argument('outbase', nargs='?', help='basename for output files (default: [pfile_name].nii.gz in cwd)')
        self.add_argument('-m', '--matfile', help='path to reconstructed data in .mat format')
        self.add_argument('-t', '--tmpdir', help='directory to use for scratch files. (Must exist and have lots of space!)')
        self.add_argument('-j', '--jobs', default=8, type=int, help='maximum number of processes to spawn')

if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    pf = PFile(args.pfile, tmpdir=args.tmpdir, max_num_jobs=args.jobs)
    if args.matfile:
        pf.set_image_data(args.matfile)
    pf.to_nii(args.outbase or os.path.basename(args.pfile))
