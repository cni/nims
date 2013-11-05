#!/usr/bin/env python
#
# @author:  Bob Dougherty
#           Gunnar Schaefer

import os
import abc
import gzip
import time
import shlex
import shutil
import logging
import argparse
import datetime
import subprocess
import numpy as np

import pfile
import nimsutil
import nimsimage
import nimsnifti

log = logging.getLogger('nimsraw')


def unpack_uid(uid):
    """Convert packed PFile UID to standard DICOM UID."""
    return ''.join([str(i-1) if i < 11 else '.' for pair in [(ord(c) >> 4, ord(c) & 15) for c in uid] for i in pair if i > 0])

def is_compressed(filepath):
    with open(filepath,'rb') as fp:
        compressed = (fp.read(2) == '\x1f\x8b')
    return compressed

def uncompress(filepath, tempdir):
    newpath = os.path.join(tempdir, os.path.basename(filepath)[:-3])
    # The following with pigz is ~4x faster than the python code above (with gzip, it's about 2.5x faster)
    if os.path.isfile('/usr/bin/pigz'):
        subprocess.call('pigz -d -c %s > %s' % (filepath, newpath), shell=True)
    elif os.path.isfile('/usr/bin/gzip') or os.path.isfile('/bin/gzip'):
        subprocess.call('gzip -d -c %s > %s' % (filepath, newpath), shell=True)
    else:
        with open(newpath, 'wb') as fd:
            with gzip.open(filepath, 'rb') as gzfile:
                fd.writelines(gzfile)
    return newpath


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
    parse_priority = 5

    file_fields = NIMSRaw.file_fields + [
            ('canonical_name', 'pfilename'),
            ]

    # TODO: Simplify init, just to parse the header
    def __init__(self, filepath, num_virtual_coils=16):
        try:
            self.compressed = is_compressed(filepath)
            self._hdr = pfile.parse(filepath, self.compressed)
        except (IOError, pfile.PFileError) as e:
            raise NIMSPFileError(str(e))
        self.filepath = os.path.abspath(filepath)
        self.dirpath = os.path.dirname(self.filepath)
        self.filename = os.path.basename(self.filepath)
        self.basename = self.filename[:-3] if self.compressed else self.filename
        self.imagedata = None
        self.fm_data = None
        self.num_vcoils = num_virtual_coils
        self.psd_name = os.path.basename(self._hdr.image.psdname.partition('\x00')[0])
        self.psd_type = nimsimage.infer_psd_type(self.psd_name)
        self.pfilename = 'P%05d' % self._hdr.rec.run_int
        self.exam_no = self._hdr.exam.ex_no
        self.series_no = self._hdr.series.se_no
        self.acq_no = self._hdr.image.scanactno
        self.exam_uid = unpack_uid(self._hdr.exam.study_uid)
        self.series_uid = unpack_uid(self._hdr.series.series_uid)
        self.series_desc = self._hdr.series.se_desc.strip('\x00')
        self.patient_id = self._hdr.exam.patidff.strip('\x00')
        self.subj_firstname, self.subj_lastname = self.parse_subject_name(self._hdr.exam.patnameff.strip('\x00'))
        self.subj_dob = self.parse_subject_dob(self._hdr.exam.dateofbirth.strip('\x00'))
        # Had to make this robust to unusual values in patsex.
        self.subj_sex = ('male', 'female')[self._hdr.exam.patsex-1] if self._hdr.exam.patsex in [1,2] else None
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
        self.num_slices = self._hdr.image.slquant
        self.num_averages = self._hdr.image.averages
        self.num_echos = self._hdr.rec.nechoes
        self.receive_coil_name = self._hdr.image.cname.strip('\x00')
        self.num_receivers = self._hdr.rec.dab[0].stop_rcv - self._hdr.rec.dab[0].start_rcv + 1
        self.operator = self._hdr.exam.operator_new.strip('\x00')
        self.protocol_name = self._hdr.series.prtcl.strip('\x00')
        self.scanner_name = self._hdr.exam.hospname.strip('\x00') + ' ' + self._hdr.exam.ex_sysid.strip('\x00')
        self.scanner_type = 'GE MEDICAL' # FIXME
        self.acquisition_type = ''
        self.size_x = self._hdr.image.dim_X  # imatrix_X
        self.size_y = self._hdr.image.dim_Y  # imatrix_Y
        self.fov = [self._hdr.image.dfov, self._hdr.image.dfov_rect]
        self.scan_type = self._hdr.image.psd_iname.strip('\x00')
        self.num_bands = 1
        self.num_mux_cal_cycle = 0
        self.num_timepoints = self._hdr.rec.npasses
        # Some sequences (e.g., muxepi) acuire more timepoints that will be available in the resulting data file.
        # The following will indicate how many to expect in the final image.
        self.num_timepoints_available = self.num_timepoints
        self.deltaTE = 0.0
        self.scale_data = False
        # Compute the voxel size rather than use image.pixsize_X/Y
        self.mm_per_vox = [self.fov[0] / self.size_y, self.fov[1] / self.size_y, self._hdr.image.slthick + self._hdr.image.scanspacing]
        image_tlhc = np.array([self._hdr.image.tlhc_R, self._hdr.image.tlhc_A, self._hdr.image.tlhc_S])
        image_trhc = np.array([self._hdr.image.trhc_R, self._hdr.image.trhc_A, self._hdr.image.trhc_S])
        image_brhc = np.array([self._hdr.image.brhc_R, self._hdr.image.brhc_A, self._hdr.image.brhc_S])
        # psd-specific params get set here
        if self.psd_type == 'spiral':
            self.num_timepoints = int(self._hdr.rec.user0)    # not in self._hdr.rec.nframes for sprt
            self.num_timepoints_available = self.num_timepoints
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
            self.num_timepoints_available = self.num_timepoints
            self.num_echoes = 1
        elif self.psd_type == 'muxepi':
            self.num_bands = int(self._hdr.rec.user6)
            self.num_mux_cal_cycle = int(self._hdr.rec.user7)
            self.band_spacing_mm = self._hdr.rec.user8
            self.num_timepoints = self._hdr.rec.npasses + self.num_bands * self._hdr.rec.ileaves * (self.num_mux_cal_cycle-1)
            self.num_timepoints_available = self._hdr.rec.npasses - self.num_bands * self._hdr.rec.ileaves * (self.num_mux_cal_cycle-1) + self.num_mux_cal_cycle
            # TODO: adjust the image.tlhc... fields to match the correct geometry.
        elif self.psd_type == 'mrs':
            self._hdr.image.scanspacing = 0.
            self.mm_per_vox = [self._hdr.rec.roileny, self._hdr.rec.roilenx, self._hdr.rec.roilenz]
            image_tlhc = np.array([self._hdr.image.ctr_R, self._hdr.image.ctr_A, self._hdr.image.ctr_S])
            image_trhc = image_tlhc + [self.mm_per_vox[0], 0., 0.]
            image_brhc = image_trhc + [0., self.mm_per_vox[2], 0.]
        # Tread carefully! Most of the stuff down here depends on various field being corrected in the
        # sequence-specific set of hacks just above. So, move things with care!

        # Note: the following is true for single-shot planar acquisitions (EPI and 1-shot spiral).
        # For multishot sequences, we need to multiply by the # of shots. And for non-planar aquisitions,
        # we'd need to multiply by the # of phase encodes (accounting for any acceleration factors).
        # Even for planar sequences, this will be wrong (under-estimate) in case of cardiac-gating.
        self.prescribed_duration = self.num_timepoints * self.tr
        self.total_num_slices = self.num_slices * self.num_timepoints
        # The actual duration can only be computed after the data are loaded. Settled for rx duration for now.
        self.duration = self.prescribed_duration
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
        # if bit 4 of rhtype(int16) is set, then fractional NEX (i.e., partial ky acquisition) was used.
        self.partial_ky = self._hdr.rec.scan_type & np.uint16(16) > 0
        self.caipi = self._hdr.rec.user13   # true: CAIPIRINHA-type acquisition; false: Direct aliasing of simultaneous slices.
        self.cap_blip_start = self._hdr.rec.user14   # Starting index of the kz blips. 0~(mux-1) correspond to -kmax~kmax.
        self.cap_blip_inc = self._hdr.rec.user15   # Increment of the kz blip index for adjacent acquired ky lines.
        self.slice_duration = self.tr * 1000 / self.num_slices
        lr_diff = image_trhc - image_tlhc
        si_diff = image_trhc - image_brhc
        if not np.all(lr_diff==0) and not np.all(si_diff==0):
            row_cosines =  lr_diff / np.sqrt(lr_diff.dot(lr_diff))
            col_cosines = -si_diff / np.sqrt(si_diff.dot(si_diff))
        else:
            row_cosines = np.array([1.,0,0])
            col_cosines = np.array([0,-1.,0])
        self.slice_order = nimsimage.SLICE_ORDER_UNKNOWN
        # FIXME: check that this is correct.
        if self._hdr.series.se_sortorder == 0:
            self.slice_order = nimsimage.SLICE_ORDER_SEQ_INC
        elif self._hdr.series.se_sortorder == 1:
            self.slice_order = nimsimage.SLICE_ORDER_ALT_INC
        slice_norm = np.array([-self._hdr.image.norm_R, -self._hdr.image.norm_A, self._hdr.image.norm_S])
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
            image_position = image_tlhc - slice_norm * slice_fov
            # FIXME: since we are reversing the slice order here, should we change the slice_order field below?
        else:
            image_position = image_tlhc
            self.reverse_slice_order = False
        if self.num_bands > 1:
            image_position = image_position - slice_norm * self.band_spacing_mm * (self.num_bands - 1.0) / 2.0

        #origin = image_position * np.array([-1, -1, 1])
        # Fix the half-voxel offset. Apparently, the p-file convention specifies coords at the
        # corner of a voxel. But DICOM/NIFTI convention is the voxel center. So offset by a half-voxel.
        origin = image_position + (row_cosines+col_cosines)*(np.array(self.mm_per_vox)/2)
        # The DICOM standard defines these two unit vectors in an LPS coordinate frame, but we'll
        # need RAS (+x is right, +y is anterior, +z is superior) for NIFTI. So, we compute them
        # such that self.row_cosines points to the right and self.col_cosines points up.
        row_cosines[0:2] = -row_cosines[0:2]
        col_cosines[0:2] = -col_cosines[0:2]
        if self.is_dwi and self.dwi_bvalue==0:
            log.warning('the data appear to be diffusion-weighted, but image.b_value is 0!')
        # The bvals/bvecs will get set later
        self.bvecs,self.bvals = (None,None)
        self.image_rotation = nimsimage.compute_rotation(row_cosines, col_cosines, slice_norm)
        self.qto_xyz = nimsimage.build_affine(self.image_rotation, self.mm_per_vox, origin)
        self.scan_type = self.infer_scan_type()
        self.aux_files = None
        super(NIMSPFile, self).__init__()

    def get_bvecs_bvals(self):
        tensor_file = os.path.join(self.dirpath, '_'+self.basename+'_tensor.dat')
        with open(tensor_file) as fp:
            uid = fp.readline().rstrip()
            ndirs = int('0'+fp.readline().rstrip())
            bvecs = np.fromfile(fp, sep=' ')
        if uid != self._hdr.series.series_uid:
            raise NIMSPFileError('tensor file UID does not match PFile UID!')
        if ndirs != self.dwi_numdirs or self.dwi_numdirs != bvecs.size / 3.:
            log.warning('tensor file numdirs does not match PFile header numdirs!')
            self.bvecs = None
            self.bvals = None
        else:
            num_nondwi = self.num_timepoints_available - self.dwi_numdirs # FIXME: assumes that all the non-dwi images are acquired first.
            bvals = np.concatenate((np.zeros(num_nondwi, dtype=float), np.tile(self.dwi_bvalue, self.dwi_numdirs)))
            bvecs = np.hstack((np.zeros((3,num_nondwi), dtype=float), bvecs.reshape(self.dwi_numdirs, 3).T))
            self.bvecs,self.bvals = nimsimage.adjust_bvecs(bvecs, bvals, self.scanner_type, self.image_rotation)

    @property
    def recon_func(self):
        if self.psd_type == 'spiral':
            return self.recon_spirec
        elif self.psd_type == 'muxepi':
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
        return int(bool(self.recon_func)) * 2 - 1   # return 1 if we can recon, else -1

    def load_all_metadata(self):
        if self.is_dwi:
            self.get_bvecs_bvals()
        super(NIMSPFile, self).load_all_metadata()

    def prep_convert(self):
        if self.psd_type == 'muxepi' and self.num_mux_cal_cycle<2:
            # Mux scan without internal calibration-- request other mux scans be handed to convert
            # to see if we can find a suitable calibration scan.
            aux_data = { 'psd': self.psd_name }
        else:
            aux_data = None
        return aux_data

    def convert(self, outbase, tempdir=None, num_jobs=8, aux_files=None):
        self.load_all_metadata()
        self.aux_files = aux_files
        if self.imagedata is None:
            self.get_imagedata(tempdir, num_jobs)
        result = (None, None)
        if self.imagedata is not None:  # catches, for example, HO Shims
            if self.reverse_slice_order:
                self.imagedata = self.imagedata[:,:,::-1,]
                if self.fm_data is not None:
                    self.fm_data = self.fm_data[:,:,::-1,]
            if self.psd_type=='spiral' and self.num_echos == 2:
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
                result = ('nifti', nimsnifti.NIMSNifti.write(self, self.imagedata, outbase))
            if self.fm_data is not None:
                nimsnifti.NIMSNifti.write(self, self.fm_data, outbase + '_B0')
        return result

    def get_imagedata(self, tempdir, num_jobs):
        if self.recon_func:
            self.recon_func(tempdir=tempdir, num_jobs=num_jobs)
        else:
            raise NIMSPFileError('Recon not implemented for this type of data')

    def load_imagedata_from_file(self, filepath):
        """ Load raw image data from a file and do some sanity checking on num slices, matrix size, etc. """
        # TODO: confirm that the voxel reordering is necessary. Maybe lean on the recon folks to standardize their voxel order?
        import scipy.io
        mat = scipy.io.loadmat(filepath)
        if 'd' in mat:
            sz = mat['d_size'].flatten().astype(int)
            slice_locs = mat['sl_loc'].flatten().astype(int) - 1
            imagedata = np.zeros(sz, np.int16)
            raw = np.atleast_3d(mat['d'])
            imagedata[:,:,slice_locs,...] = raw[::-1,...].round().clip(-32768, 32767).astype(np.int16)
        elif 'MIP_res' in mat:
            imagedata = np.atleast_3d(mat['MIP_res'])
            imagedata = imagedata.transpose((1,0,2,3))[::-1,::-1,:,:]
        if imagedata.ndim == 3:
            imagedata = imagedata.reshape(imagedata.shape + (1,))
        return imagedata

    def update_imagedata(self, imagedata):
        self.imagedata = imagedata
        if self.imagedata.shape[0] != self.size_x or self.imagedata.shape[1] != self.size_y:
            log.warning('Image matrix discrepancy. Fixing the header, assuming imagedata is correct...')
            self.size_x = self.imagedata.shape[0]
            self.size_y = self.imagedata.shape[1]
            self.mm_per_vox[0] = self.fov[0] / self.size_x
            self.mm_per_vox[1] = self.fov[1] / self.size_y
        if self.imagedata.shape[2] != self.num_slices * self.num_bands:
            log.warning('Image slice count discrepancy. Fixing the header, assuming imagedata is correct...')
            self.num_slices = self.imagedata.shape[2]
        if self.imagedata.shape[3] != self.num_timepoints:
            log.warning('Image time frame discrepancy (header=%d, array=%d). Fixing the header, assuming imagedata is correct...'
                    % (self.num_timepoints, self.imagedata.shape[3]))
            self.num_timepoints = self.imagedata.shape[3]
        self.duration = self.num_timepoints * self.tr # FIXME: maybe need self.num_echoes?

    def recon_hoshim(self, tempdir, num_jobs):
        log.debug('Cannot recon HO SHIM data')

    def recon_basic(self, tempdir, num_jobs):
        log.debug('Cannot recon BASIC data')

    def recon_spirec(self, tempdir, num_jobs):
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
            cmd = 'spirec -l --rotate -90 --magfile --savefmap2 --b0navigator -r %s -t %s' % (pfile_path, 'recon')
            log.debug(cmd)
            subprocess.call(shlex.split(cmd), cwd=temp_dirpath, stdout=open('/dev/null', 'w'))  # run spirec to generate .mag and fieldmap files

            self.imagedata = np.fromfile(file=basepath+'.mag_float', dtype=np.float32).reshape([self.size_x,self.size_y,self.num_timepoints,self.num_echos,self.num_slices],order='F').transpose((0,1,4,2,3))
            if os.path.exists(basepath+'.B0freq2') and os.path.getsize(basepath+'.B0freq2')>0:
                self.fm_data = np.fromfile(file=basepath+'.B0freq2', dtype=np.float32).reshape([self.size_x,self.size_y,self.num_echos,self.num_slices],order='F').transpose((0,1,3,2))

    def find_mux_cal_file(self):
        cal_file = []
        if self.num_mux_cal_cycle<2 and self.aux_files!=None and len(self.aux_files)>0:
            candidates = [pf for pf in [(NIMSPFile(f),f) for f in self.aux_files] if pf[0].num_mux_cal_cycle>=2]
            if len(candidates)==1:
                cal_file = candidates[0][1].encode()
            elif len(candidates)>1:
                series_num_diff = np.array([c[0].series_no for c in candidates]) - self.series_no
                closest = np.min(np.abs(series_num_diff))==np.abs(series_num_diff)
                # there may be more than one. We prefer the prior scan:
                closest = np.where(np.min(series_num_diff[closest])==series_num_diff)[0][0]
                cal_file = candidates[closest][1].encode()
        if len(cal_file)>0:
            cal_compressed = is_compressed(cal_file)
            cal_basename = cal_file[:-3] if cal_compressed else cal_file
            cal_ref_file  = os.path.join(os.path.dirname(cal_basename), '_'+os.path.basename(cal_basename)+'_ref.dat')
            cal_vrgf_file = os.path.join(os.path.dirname(cal_basename), '_'+os.path.basename(cal_basename)+'_vrgf.dat')
        else:
            cal_compressed = False
            cal_ref_file = ''
            cal_vrgf_file = ''
        # Make sure we return an empty string when none is found.
        if not cal_file:
            cal_file = ''
        return cal_file,cal_ref_file,cal_vrgf_file,cal_compressed

    def recon_mux_epi(self, tempdir, num_jobs, timepoints=[], octave_bin='octave'):
        start_sec = time.time()
        """Do mux_epi image reconstruction and populate self.imagedata."""
        ref_file  = os.path.join(self.dirpath, '_'+self.basename+'_ref.dat')
        vrgf_file = os.path.join(self.dirpath, '_'+self.basename+'_vrgf.dat')
        if not os.path.isfile(ref_file) or not os.path.isfile(vrgf_file):
            raise NIMSPFileError('dat files not found')
        # See if external calibration data files are needed:
        cal_file,cal_ref_file,cal_vrgf_file,cal_compressed = self.find_mux_cal_file()
        # HACK to force SENSE recon for caipi data
        sense_recon = 1 if 'CAIPI' in self.series_desc else 0

        with nimsutil.TempDir(dir=tempdir) as temp_dirpath:
            log.info('Running %d v-coil mux recon on %s in tempdir %s with %d jobs (sense=%d).'
                    % (self.num_vcoils, self.filepath, tempdir, num_jobs, sense_recon))
            if self.compressed:
                shutil.copy(ref_file, os.path.join(temp_dirpath, os.path.basename(ref_file)))
                shutil.copy(vrgf_file, os.path.join(temp_dirpath, os.path.basename(vrgf_file)))
                pfile_path = uncompress(self.filepath, temp_dirpath)
            else:
                pfile_path = self.filepath
            if cal_file and cal_compressed:
                shutil.copy(cal_ref_file, os.path.join(temp_dirpath, os.path.basename(cal_ref_file)))
                shutil.copy(vrgf_file, os.path.join(temp_dirpath, os.path.basename(cal_vrgf_file)))
                cal_file = uncompress(cal_file, temp_dirpath)
            recon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'mux_epi_recon'))
            outname = os.path.join(temp_dirpath, 'sl')

            # Spawn the desired number of subprocesses until all slices have been spawned
            mux_recon_jobs = []
            slice_num = 0
            while slice_num < self.num_slices:
                num_running_jobs = sum([job.poll()==None for job in mux_recon_jobs])
                if num_running_jobs < num_jobs:
                    # Recon each slice separately. Note the slice_num+1 to deal with matlab's 1-indexing.
                    # Use 'str' on timepoints so that an empty array will produce '[]'
                    cmd = ('%s --no-window-system -p %s --eval \'mux_epi_main("%s", "%s_%03d.mat", "%s", %d, %s, %d, 0, %d);\''
                        % (octave_bin, recon_path, pfile_path, outname, slice_num, cal_file, slice_num + 1, str(timepoints), self.num_vcoils, sense_recon))
                    log.debug(cmd)
                    mux_recon_jobs.append(subprocess.Popen(args=shlex.split(cmd), stdout=open('/dev/null', 'w')))
                    slice_num += 1
                else:
                    time.sleep(1.)

            # Now wait for all the jobs to finish
            for job in mux_recon_jobs:
                job.wait()

            # Load the first slice to initialize the image array
            img = self.load_imagedata_from_file("%s_%03d.mat" % (outname, 0))
            for slice_num in range(1, self.num_slices):
                new_img = self.load_imagedata_from_file("%s_%03d.mat" % (outname, slice_num))
                # Allow for a partial last timepoint. This sometimes happens when the user aborts.
                t = min(img.shape[-1], new_img.shape[-1])
                img[...,0:t] += new_img[...,0:t]

            self.update_imagedata(img)
            elapsed = time.time() - start_sec
            log.info('Mux recon of %s with %d v-coils finished in %0.2f minutes using %d jobs.'
                      % (self.filepath, self.num_vcoils,  elapsed/60., min(num_jobs, self.num_slices)))


    def recon_mrs(self, tempdir, num_jobs):
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
        self.add_argument('-v', '--vcoils', default=0, type=int, help='number of virtual coils (0=all)')
        self.add_argument('-c', '--auxfile', help='path to auxillary files (e.g., mux calibration p-files)')

if __name__ == '__main__':
    args = ArgumentParser().parse_args()
    nimsutil.configure_log()
    pf = NIMSPFile(args.pfile, num_virtual_coils=args.vcoils)
    if args.matfile:
        pf.update_imagedata(pf.load_imagedata_from_file(args.matfile))
    pf.convert(args.outbase or os.path.basename(args.pfile), tempdir=args.tempdir, num_jobs=args.jobs, aux_files=[args.auxfile])

