#!/usr/bin/env python
#
# @author:  Bob Dougherty
#           Gunnar Schaefer

import os
import abc
import gzip
#import h5py
import time
import shlex
import shutil
import logging
import nibabel
import argparse
import datetime
import subprocess
import numpy as np

import nimsutil
import nimsimage
import nimsnifti
import pfheader

log = logging.getLogger('nimsraw')


def unpack_uid(uid):
    """Convert packed PFile UID to standard DICOM UID."""
    return ''.join([str(i-1) if i < 11 else '.' for pair in [(ord(c) >> 4, ord(c) & 15) for c in uid] for i in pair if i > 0])


class NIMSRawError(nimsimage.NIMSImageError):
    pass


class NIMSRaw(nimsimage.NIMSImage):

    __metaclass__ = abc.ABCMeta


class NIMSPFileError(NIMSRawError):
    pass


class NIMSPFile(NIMSRaw):
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

    # TODO: Simplify init, just to parse the header
    def __init__(self, filepath, tmpdir=None, max_num_jobs=8, num_virtual_coils=0):
        try:
            with open(filepath,'rb') as fp:
                self.compressed = (fp.read(2) == '\x1f\x8b')
            fp = gzip.open(filepath, 'rb') if self.compressed else open(filepath, 'rb')
            self._hdr = pfheader.get_header(fp)
            fp.close()
        except (IOError, pfheader.PFHeaderError) as e:
            raise NIMSPFileError(e)
        self.filepath = os.path.abspath(filepath)
        self.dirpath = os.path.dirname(self.filepath)
        self.filename = os.path.basename(self.filepath)
        self.basename = self.filename[:-3] if self.compressed else self.filename

        self.max_num_jobs = max_num_jobs
        self.tmpdir = tmpdir
        self.imagedata = None
        self.fm_data = None
        self.num_vcoils = num_virtual_coils

        self.psd_name = os.path.basename(self._hdr.image.psdname.partition('\x00')[0])
        if self.psd_name == 'sprt':
            self.psd_type = 'spiral'
        elif self.psd_name == 'sprl_hos':
            self.psd_type = 'hoshim'
        elif self.psd_name == 'basic':
            self.psd_type = 'basic'
        elif 'mux' in self.psd_name.lower(): # multi-band EPI!
            self.psd_type = 'mux'
        elif self.psd_name == 'Probe-MEGA':
            self.psd_type = 'mrs'
        else:
            self.psd_type = 'unknown'

        self.exam_no = self._hdr.exam.ex_no
        self.series_no = self._hdr.series.se_no
        self.acq_no = self._hdr.image.scanactno
        self.exam_uid = unpack_uid(self._hdr.exam.study_uid)
        self.series_uid = unpack_uid(self._hdr.series.series_uid)
        self.series_desc = self._hdr.series.se_desc.strip('\x00')
        self.patient_id = self._hdr.exam.patidff.strip('\x00')
        self.subj_firstname, self.subj_lastname = self.parse_subject_name(self._hdr.exam.patnameff.strip('\x00'))
        self.subj_dob = self.parse_subject_dob(self._hdr.exam.dateofbirth.strip('\x00'))
        self.subj_sex = (None, 'male', 'female')[self._hdr.exam.patsex]
        if self._hdr.image.im_datetime > 0:
            self.timestamp = datetime.datetime.utcfromtimestamp(self._hdr.image.im_datetime)
        else:   # HOShims don't have self._hdr.image.im_datetime
            month, day, year = map(int, self._hdr.rec.scan_date.strip('\x00').split('/'))
            hour, minute = map(int, self._hdr.rec.scan_time.strip('\x00').split(':'))
            self.timestamp = datetime.datetime(year + 1900, month, day, hour, minute) # GE's epoch begins in 1900

        self.ti = self._hdr.image.ti / 1e6
        self.te = self._hdr.image.te / 1e6
        self.tr = self._hdr.image.tr / 1e6  # tr in seconds
        self.flip_angle = float(self._hdr.image.mr_flip)
        self.pixel_bandwidth = self._hdr.rec.bw
        # Note: the freq/phase dir isn't meaningful for spiral trajectories.
        self.phase_encode = 1 if self._hdr.image.freq_dir == 0 else 0
        self.mt_offset_hz = self._hdr.image.offsetfreq

        self.num_slices = self._hdr.rec.nslices
        self.num_averages = self._hdr.image.averages
        self.num_echos = self._hdr.rec.nechoes
        self.receive_coil_name = self._hdr.image.cname.strip('\x00')
        self.num_receivers = self._hdr.rec.dab[0].stop_rcv - self._hdr.rec.dab[0].start_rcv + 1
        self.patient_id = self._hdr.exam.patidff.strip('\x00')
        self.operator = self._hdr.exam.operator_new.strip('\x00')
        self.protocol_name = self._hdr.series.prtcl.strip('\x00')
        self.scanner_name = self._hdr.exam.hospname.strip('\x00') + ' ' + self._hdr.exam.ex_sysid.strip('\x00')
        self.scanner_type = 'GE' # FIXME
        self.acquisition_type = ''

        self.size_x = self._hdr.image.dim_X  # imatrix_X
        self.size_y = self._hdr.image.dim_Y  # imatrix_Y
        self.fov = [self._hdr.image.dfov, self._hdr.image.dfov_rect]
        self.scan_type = self._hdr.image.psd_iname.strip('\x00')
        self.num_bands = 1
        self.num_mux_cal_cycle = 0

        self.num_timepoints = self._hdr.rec.npasses
        self.deltaTE = 0.0
        self.scale_data = False

        image_tlhc = np.array([self._hdr.image.tlhc_R, self._hdr.image.tlhc_A, -self._hdr.image.tlhc_S])
        image_trhc = np.array([self._hdr.image.trhc_R, self._hdr.image.trhc_A, -self._hdr.image.trhc_S])
        image_brhc = np.array([self._hdr.image.brhc_R, self._hdr.image.brhc_A, -self._hdr.image.brhc_S])

        if self.psd_type == 'spiral':
            self.num_timepoints = int(self._hdr.rec.user0)    # not in self._hdr.rec.nframes for sprt
            self.deltaTE = self._hdr.rec.user15
            self.band_spacing = 0
            self.scale_data = True
            # spiral is always a square encode based on the frequency encode direction (size_x)
            # Atsushi also likes to round up to the next higher power of 2.
            # self.size_x = int(pow(2,ceil(log2(pf.size_x))))
            # The rec.im_size field seems to have the correct reconned image size, but
            # this isn't guaranteed to be correct, as Atsushi's recon does whatever it
            # damn well pleases. Maybe we could add a check to infer the image size,
            # assuming it's square?
            self.size_x = self.size_y = self._hdr.rec.im_size
        elif self.psd_type == 'basic':
            # first 6 are ref scans, so ignore those. Also, two acquired timepoints are used
            # to generate each reconned time point.
            self.num_timepoints = (self._hdr.rec.npasses * self._hdr.rec.nechoes - 6) / 2
            self.num_echoes = 1
        elif self.psd_type == 'mux':
            self.num_bands = int(self._hdr.rec.user6)
            self.num_mux_cal_cycle = int(self._hdr.rec.user7)
            self.band_spacing_mm = self._hdr.rec.user8
            self.num_slices = self._hdr.image.slquant * self.num_bands
            self.num_timepoints = self._hdr.rec.npasses - self.num_bands*self.num_mux_cal_cycle + self.num_mux_cal_cycle
            # TODO: adjust the image.tlhc... fields to match the correct geometry.
        elif self.psd_type == 'mrs':
            self._hdr.image.scanspacing = 0.
            self.fov = [self._hdr.rec.roilenx, self._hdr.rec.roileny]
            image_tlhc = np.array([self._hdr.rec.roilocx, self._hdr.rec.roilocy, self._hdr.rec.roilocz])
            image_trhc = np.array([self._hdr.rec.roilocx + self._hdr.rec.roilenx, self._hdr.rec.roilocy, self._hdr.rec.roilocz])
            image_brhc = np.array([self._hdr.rec.roilocx + self._hdr.rec.roilenx, self._hdr.rec.roilocy + self._hdr.rec.roileny, self._hdr.rec.roilocz])

        self.total_num_slices = self.num_slices * self.num_timepoints
        # Note: the following is true for single-shot planar acquisitions (EPI and 1-shot spiral).
        # For multishot sequences, we need to multiply by the # of shots. And for non-planar aquisitions,
        # we'd need to multiply by the # of phase encodes (accounting for any acceleration factors).
        # Even for planar sequences, this will be wrong (under-estimate) in case of cardiac-gating.
        self.prescribed_duration = datetime.timedelta(seconds=(self.num_timepoints * self.tr))
        # The actual duration can only be computed after the data are loaded. Settled for rx duration for now.
        self.duration = self.prescribed_duration
        # Compute the voxel size rather than use image.pixsize_X/Y
        self.mm_per_vox = np.array([self.fov[0] / self._hdr.image.dim_X, self.fov[1] / self._hdr.image.dim_Y, self._hdr.image.slthick + self._hdr.image.scanspacing])

        lr_diff = image_tlhc - image_trhc
        si_diff = image_trhc - image_brhc
        if not np.all(lr_diff == 0):
            self.row_cosines = lr_diff / np.sqrt(lr_diff.dot(lr_diff))
            self.col_cosines = si_diff / np.sqrt(si_diff.dot(si_diff))
        # The DICOM standard defines these two unit vectors in an LPS coordinate frame, but we'll
        # need RAS (+x is right, +y is anterior, +z is superior) for NIFTI. So, we compute them
        # such that self.row_cosines points to the right and self.col_cosines points up.
        # Not sure if we need to negate the slice_norm. From the NIFTI-1 header:
        #     The third column of R will be either the cross-product of the first 2 columns or
        #     its negative. It is possible to infer the sign of the 3rd column by examining
        #     the coordinates in DICOM attribute (0020,0032) "Image Position (Patient)" for
        #     successive slices. However, this method occasionally fails for reasons that I
        #     (RW Cox) do not understand.

        self.effective_echo_spacing = self._hdr.image.effechospace / 1e6
        self.phase_encode_undersample = 1. / self._hdr.rec.ileaves
        # TODO: Set this correctly! (it's in the dicom at (0x0043, 0x1083))
        self.slice_encode_undersample = 1.
        self.acquisition_matrix = [self._hdr.rec.rc_xres, self._hdr.rec.rc_yres]
        # Diffusion params
        self.dwi_numdirs = self._hdr.rec.numdifdirs
        # You might think that the b-valuei for diffusion scans would be stored in self._hdr.image.b_value.
        # But alas, this is GE. Apparently, that var stores the b-value of the just the first image, which is
        # usually a non-dwi. So, we had to modify the PSD and stick the b-value into an rhuser CV. Sigh.
        self.dwi_bvalue = self._hdr.rec.user22
        self.is_dwi = True if self.dwi_numdirs >= 6 else False
        if self.is_dwi and self.dwi_bvalue==0:
            log.warning('the data appear to be diffusion-weighted, but image.b_value is 0!')

        # can also get slice_norm from: slice_norm = np.cross(self.row_cosines, self.col_cosines)
        self.slice_norm = np.array([self._hdr.image.norm_R, self._hdr.image.norm_A, self._hdr.image.norm_S])

        self.slice_duration = self.tr * 1000 / self.num_slices
        self.slice_order = nimsimage.SLICE_ORDER_UNKNOWN
        # FIXME: check that this is correct.
        if self._hdr.series.se_sortorder == 0:
            self.slice_order = nimsimage.SLICE_ORDER_SEQ_INC
        elif self._hdr.series.se_sortorder == 1:
            self.slice_order = nimsimage.SLICE_ORDER_ALT_INC

        # This is either the first slice tlhc (image_tlhc) or the last slice tlhc. How to decide?
        # And is it related to wheather I have to negate the slice_norm?
        # Tuned this empirically by comparing spiral and EPI data with the same Rx.
        # Everything seems reasonable, except the test for axial orientation (start_ras==S|I).
        # I have no idea why I need that! But the flipping only seems necessary for axials, not
        # coronals or the few obliques I've tested.
        # FIXME: haven't tested sagittals!
        if (self._hdr.series.start_ras=='S' or self._hdr.series.start_ras=='I') and self._hdr.series.start_loc > self._hdr.series.end_loc:
            self.reverse_slice_order = True
            slice_fov = np.abs(self._hdr.series.start_loc - self._hdr.series.end_loc)
            self.image_position = image_tlhc - self.slice_norm * slice_fov
            # FIXME: since we are reversing the slice order here, should we change the slice_order field below?
        else:
            self.image_position = image_tlhc
            self.reverse_slice_order = False

        if self.num_bands > 1:
            self.image_position = self.image_position - self.slice_norm * self.band_spacing_mm * (self.num_bands - 1.0) / 2.0

        # if bit 4 of rhtype(int16) is set, then fractional NEX (i.e., partial ky acquisition) was used.
        self.partial_ky = self._hdr.rec.scan_type & np.uint16(16) > 0
        self.caipi = self._hdr.rec.user13   # true: CAIPIRINHA-type acquisition; false: Direct aliasing of all simultaneous slices.
        self.cap_blip_start = self._hdr.rec.user14   # Starting index of the kz blips. 0~(mux-1) correspond to -kmax~kmax.
        self.cap_blip_inc = self._hdr.rec.user15   # Increment of the kz blip index for adjacent acquired ky lines.
        super(NIMSPFile, self).__init__()

    def get_bvals_bvecs(self):
        tensor_file = os.path.join(self.dirpath, '_'+self.basename+'_tensor.dat')
        with open(tensor_file) as fp:
            uid = fp.readline().rstrip()
            ndirs = int(fp.readline().rstrip())
            bvecs = np.fromfile(fp, sep=' ')
        if uid != self._hdr.series.series_uid:
            raise NIMSPFileError('tensor file UID does not match PFile UID!')
        if ndirs != self.dwi_numdirs or self.dwi_numdirs != bvecs.size / 3.:
            raise NIMSPFileError('tensor file numdirs does not match PFile header numdirs!')
        num_nondwi = self.num_timepoints - self.dwi_numdirs # FIXME: assumes that all the non-dwi images are acquired first.
        bvals = np.concatenate((np.zeros(num_nondwi, dtype=float), np.tile(self.dwi_bvalue, self.dwi_numdirs)))
        bvecs = np.hstack((np.zeros((3,num_nondwi), dtype=float), bvecs.reshape(self.dwi_numdirs, 3).T))
        return bvals, bvecs

    @property
    def recon_func(self):
        if self.psd_type == 'siral':
            return self.recon_spirec
        elif self.psd_type == 'mux':
            return self.recon_mux_epi
        elif self.psd_type == 'mrs':
            return self.recon_mrs
        elif self.psd_type == 'hoshim':
            return self.recon_hoshim
        elif self.psd_type == 'basic':
            return self.recon_basic
        else:
            return None

    @property
    def priority(self):
        return int(bool(self.recon_func)) * 2 - 1   # return >0 if we can recon, else 0

    def convert(self, outbase, tempdir=None, jobs=8):
        if self.recon_func:
            self.recon_func()
        else:
            raise NIMSPFileError('Recon not implemented for this type of data')

        result = (None, None)
        if self.imagedata is not None:  # catches, for example, HO Shims

            if self.reverse_slice_order:
                self.imagedata = self.imagedata[:,:,::-1,]
                if self.fm_data is not None:
                    self.fm_data = self.fm_data[:,:,::-1,]

            self.bvecs, self.bvals = get_bvals_bvecs() if self.is_dwi else (None, None)
            if self.num_echos == 1:
                result = ('nifti', nimsnifti.NIMSNifti.write(self, self.imagedata, outbase))
            elif self.psd_type=='spiral' and self.num_echos == 2:
                # Uncomment to save spiral in/out
                #nimsnifti.NIMSNifti.write(self, self.imagedata[:,:,:,:,0], outbase + '_in')
                #nimsnifti.NIMSNifti.write(self, self.imagedata[:,:,:,:,1], outbase + '_out')
                # FIXME: Do a more robust test for spiralio!
                # Assume spiralio, so do a weighted average of the two echos.
                # FIXME: should do a quick motion correction here
                w_in = np.mean(self.imagedata[:,:,:,:,0], 3)
                w_out = np.mean(self.imagedata[:,:,:,:,1], 3)
                inout_sum = w_in + w_out
                w_in = w_in / inout_sum
                w_out = w_out / inout_sum
                avg = np.zeros(self.imagedata.shape[0:4])
                for tp in range(self.imagedata.shape[3]):
                    avg[:,:,:,tp] = w_in*self.imagedata[:,:,:,tp,0] + w_out*self.imagedata[:,:,:,tp,1]
                result = ('nifti', nimsnifti.NIMSNifti.write(self, avg, outbase))
            else:
                main_file = None
                for echo in range(self.num_echos):
                    result = ('nifti', nimsnifti.NIMSNifti.write(self, self.imagedata[:,:,:,:,echo], outbase + '_echo%02d' % (echo+1)))
            if self.fm_data is not None:
                nimsnifti.NIMSNifti.write(self, self.fm_data, outbase + '_B0')
        return result

    def load_imagedata(self, filepath):
        """ Load raw image data from a file and do some sanity checking on num slices, matrix size, etc. """
        # TODO: confirm that the voxel reordering is necessary. Maybe lean on the recon folks to standardize their voxel order?
        mat = h5py.File(filepath, 'r')
        if 'd' in mat:
            imagedata = np.atleast_3d(mat['d'].items()[1][1].value).transpose((3,2,1,0))[::-1,:,:,:]
        elif 'MIP_res' in mat:
            imagedata = np.atleast_3d(mat['MIP_res'].items()[1][1].value).transpose((1,0,2,3))[::-1,::-1,:,:]
        if imagedata.ndim == 3:
            imagedata = imagedata.reshape(imagedata.shape + (1,))
        mat.close()
        return imagedata

    def update_imagedata(self, imagedata):
        self.imagedata = imagedata
        if self.imagedata.shape[0] != self.size_x or self.imagedata.shape[1] != self.size_y:
            log.warning('Image matrix discrepancy. Fixing the header, assuming imagedata is correct...')
            self.size_x = self.imagedata.shape[0]
            self.size_y = self.imagedata.shape[1]
            self.mm_per_vox[0] = float(self.fov[0] / self.size_x)
            self.mm_per_vox[1] = float(self.fov[1] / self.size_y)
        if self.imagedata.shape[2] != self.num_slices:
            log.warning('Image slice count discrepancy. Fixing the header, assuming imagedata is correct...')
            self.num_slices = self.imagedata.shape[2]
        if self.imagedata.shape[3] != self.num_timepoints:
            log.warning('Image time frame discrepancy (header=%d, array=%d). Fixing the header, assuming imagedata is correct...'
                    % (self.num_timepoints, self.imagedata.shape[3]))
            self.num_timepoints = self.imagedata.shape[3]
        self.duration = self.num_timepoints * self.tr # FIXME: maybe need self.num_echoes?

    def recon_hoshim(self, tempdir=None, executable=None):
        log.debug('Cannot recon HO SHIM data')

    def recon_basic(self, tempdir=None, executable=None):
        log.debug('Cannot recon BASIC data')

    def recon_spirec(self, tempdir=None, executable='spirec'):
        """Do spiral image reconstruction and populate self.imagedata."""
        with nimsutil.TempDir(dir=tempdir) as temp_dirpath:
            if self.compressed:
                pfile_path = os.path.join(temp_dirpath, self.basename)
                with open(pfile_path, 'wb') as fd:
                    with gzip.open(self.filepath, 'rb') as gzfile:
                        fd.writelines(gzfile)
            else:
                pfile_path = self.filepath
            basepath = os.path.join(temp_dirpath, 'recon')
            cmd = '%s -l --rotate -90 --magfile --savefmap2 --b0navigator -r %s -t %s' % (executable, pfile_path, 'recon')
            log.debug(cmd)
            subprocess.call(shlex.split(cmd), cwd=temp_dirpath, stdout=open('/dev/null', 'w'))  # run spirec to generate .mag and fieldmap files

            self.imagedata = np.fromfile(file=basepath+'.mag_float', dtype=np.float32).reshape([self.size_x,self.size_y,self.num_timepoints,self.num_echos,self.num_slices],order='F').transpose((0,1,4,2,3))
            if os.path.exists(basepath+'.B0freq2') and os.path.getsize(basepath+'.B0freq2')>0:
                self.fm_data = np.fromfile(file=basepath+'.B0freq2', dtype=np.float32).reshape([self.size_x,self.size_y,self.num_echos,self.num_slices],order='F').transpose((0,1,3,2))

    def recon_mux_epi(self, tempdir=None, executable='octave', timepoints=[]):
        """Do mux_epi image reconstruction and populate self.imagedata."""
        ref_file  = os.path.join(self.dirpath, '_'+self.basename+'_ref.dat')
        vrgf_file = os.path.join(self.dirpath, '_'+self.basename+'_vrgf.dat')
        if not os.path.isfile(ref_file) or not os.path.isfile(vrgf_file):
            raise NIMSPFileError('dat files not found')
        with nimsutil.TempDir(dir=self.tmpdir) as temp_dirpath:
            if self.compressed:
                shutil.copy(ref_file, os.path.join(temp_dirpath, os.path.basename(ref_file)))
                shutil.copy(vrgf_file, os.path.join(temp_dirpath, os.path.basename(vrgf_file)))
                pfile_path = os.path.join(temp_dirpath, self.basename)
                with open(pfile_path, 'wb') as fd:
                    with gzip.open(self.filepath, 'rb') as gzfile:
                        fd.writelines(gzfile)
            else:
                pfile_path = self.filepath
            recon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'mux_epi_recon'))
            outname = os.path.join(temp_dirpath, 'sl')

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
                            % (executable, recon_path, pfile_path, outname, slice_num, slice_num + 1, str(timepoints), self.num_vcoils))
                    log.debug(cmd)
                    mux_recon_jobs.append(subprocess.Popen(args=shlex.split(cmd), stdout=open('/dev/null', 'w')))
                    slice_num += 1
                else:
                    time.sleep(1.)

            # Now wait for all the jobs to finish
            for job in mux_recon_jobs:
                job.wait()

            # Load the first slice to initialize the image array
            img = self.load_imagedata("%s_%03d.mat" % (outname, 0))
            for slice_num in range(1, num_muxed_slices):
                new_img = self.load_imagedata("%s_%03d.mat" % (outname, slice_num))
                # Allow for a partial last timepoint. This sometimes happens when the user aborts.
                img[...,0:new_img.shape[-1]] += new_img
            self.update_imagedata(img)

    def recon_mrs(self, tempdir=None, executable=None):
        """Currently just loads raw spectro data into self.imagedata so that we can save it in a nifti."""
        # Reorder the data to be in [frame, num_frames, slices, passes (repeats), echos, coils]
        # This roughly complies with the nifti standard of x,y,z,time,[then whatever].
        # Note that the "frame" is the line of k-space and thus the FID timeseries.
        self.imagedata = self.get_rawdata().transpose([0,5,3,1,2,4])

    def get_rawdata(self, slices=None, passes=None, coils=None, echos=None, frames=None):
        """
        Reads and returns a chunck of data from the p-file. Specify the slices,
        timepoints, coils, and echos that you want. None means you get all of
        them. The default of all Nones will return all data.
        (based on https://github.com/cni/MRS/blob/master/MRS/files.py)
        """

        n_frames = self._hdr.rec.nframes + self._hdr.rec.hnover
        n_echoes = self._hdr.rec.nechoes
        n_slices = self._hdr.rec.nslices / self._hdr.rec.npasses
        n_coils = self.num_receivers
        n_passes = self._hdr.rec.npasses
        frame_sz = self._hdr.rec.frame_size

        if passes == None: passes = range(n_passes)
        if coils == None: coils = range(n_coils)
        if slices == None: slices = range(n_slices)
        if echos == None: echos = range(n_echoes)
        if frames == None: frames = range(n_frames)

        # Size (in bytes) of each sample:
        ptsize = self._hdr.rec.point_size
        data_type = [np.int16, np.int32][ptsize/2 - 1]

        # This is double the size as above, because the data is complex:
        frame_bytes = 2 * ptsize * frame_sz

        echosz = frame_bytes * (1 + n_frames)
        slicesz = echosz * n_echoes
        coilsz = slicesz * n_slices
        passsz = coilsz * n_coils

        # Byte-offset to get to the data:
        offset = self._hdr.rec.off_data
        fp = gzip.open(self.filepath, 'rb') if self.compressed else open(self.filepath, 'rb')
        data = np.zeros((frame_sz, len(frames), len(echos), len(slices), len(coils), len(passes)), dtype=np.complex)
        for pi,passidx in enumerate(passes):
            for ci,coilidx in enumerate(coils):
                for si,sliceidx in enumerate(slices):
                    for ei,echoidx in enumerate(echos):
                        for fi,frameidx in enumerate(frames):
                            fp.seek(passidx*passsz + coilidx*coilsz + sliceidx*slicesz + echoidx*echosz + (frameidx+1)*frame_bytes + offset)
                            # Unfortunately, numpy fromfile doesn't like gzip file objects. But we can
                            # safely load each chunk into RAM, since frame_sz is never very big.
                            #dr = np.fromfile(fp, data_type, frame_sz * 2)
                            dr = np.fromstring(fp.read(frame_bytes), data_type)
                            dr = np.reshape(dr, (-1, 2)).T
                            data[:, fi, ei, si, ci, pi] = dr[0] + dr[1]*1j
        fp.close()
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
        self.add_argument('-t', '--tempdir', help='directory to use for scratch files (must exist and have lots of space!)')
        self.add_argument('-j', '--jobs', default=8, type=int, help='maximum number of processes to spawn')

if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    nimsutil.configure_log()
    pf = NIMSPFile(args.pfile)
    if args.matfile:
        pf.update_imagedata(pf.load_imagedata(args.matfile))
    pf.convert(args.outbase or os.path.basename(args.pfile), args.tempdir, args.jobs)
